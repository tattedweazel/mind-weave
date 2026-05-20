"""WorkflowExecutor `_run_*` skill methods split from executor.py for maintainability."""

import asyncio
import base64
import json
import time
import uuid
from datetime import timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import or_
from sqlmodel import col, select

from app.core.config import settings
from app.core.logging import logger
from app.core.user_api_keys_crypto import decrypt_api_keys_store
from app.domain.audio_file_validation import ValidatedAudioFile
from app.domain.persona_lm_options import persona_lm_chat_options
from app.domain.schemas import (
    AudioFileInputSkillNode,
    AudioNodeOutput,
    CalendarListEventsSkillNode,
    GoogleDocsGetDocumentSkillNode,
    CaptureUrlSnapshotSkillNode,
    DictionaryNodeOutput,
    FetchUrlSkillNode,
    GmailListMessagesSkillNode,
    GraphEdge,
    ListNodeOutput,
    MultimodalLLMCallSkillNode,
    NodeOutputUnion,
    ResponseNodeOutput,
    SimpleLLMCallSkillNode,
    StringNodeOutput,
    TextToSpeechSkillNode,
    TranscribeAudioSkillNode,
    TranscribeFileSkillNode,
)
from app.domain.services.url_fetch_cache_service import get_cached_payload, upsert_success_cache
from app.domain.services.url_snapshot_cache_service import create_artifact, get_cache_artifact, upsert_cache
from app.domain.workflow_executor.capture_url_snapshot_runtime import (
    build_success_output_from_artifact,
    strip_internal_keys_for_output,
)
from app.domain.workflow_executor.capture_url_snapshot_runtime import (
    compute_cache_key as compute_snapshot_cache_key,
)
from app.domain.workflow_executor.multimodal_llm_runtime import (
    MultimodalLLMInputError,
    build_openai_image_parts_from_artifacts,
    image_artifact_refs_for_log,
    normalize_images_input,
)
from app.domain.workflow_executor.schema_normalizer import normalize_schema_for_structured_output
from app.domain.workflow_executor.transcribe_pending import (
    TranscribeUpload,
    TranscribeWaitKey,
    cancel_transcribe_wait,
    register_transcribe_wait,
)
from app.integrations.gmail_query import (
    append_category_q_clauses,
    build_messages_list_q,
    coerce_bool_unread,
    normalize_gmail_exclude_categories,
    normalize_gmail_inbox_focus,
)
from app.persistence.tables import (
    AudioFileArtifact,
    Persona,
    Structure,
    TtsModelArtifact,
    User,
    VoiceSample,
)
from app.providers.lmstudio import LMStudioModelNotMultimodalError
from app.providers.lmstudio_http import resolve_lmstudio_bearer
from app.providers.stt_bridge import SttBridgeError as SttBridgeHttpError
from app.providers.transcription import (
    TranscriptionOptions,
    TranscriptionProviderError,
    enabled_provider_ids,
)
from app.providers.transcription.keys import resolve_assemblyai_api_key
from app.providers.tts_bridge import TtsBridgeError

from .diagnostics import (
    GMAIL_MESSAGE_BODY_MAX_CHARS,
    curated_gmail_message_from_full_api,
    curated_google_calendar_event,
    merge_skill_diagnostics,
    truncate_gmail_messages_list_response,
    truncate_google_calendar_events_list_response,
)
from app.integrations.google_docs import GoogleDocsUrlParseError, parse_google_docs_url_or_id
from app.integrations.google_workflow_connection import (
    GOOGLE_WORKFLOW_CONNECTION_REQUIRED_MSG,
    get_user_workflow_google_connection,
)

from .google_docs_curate import build_document_payload, truncate_google_docs_get_response
from .fetch_url_runtime import compute_cache_key, normalize_headers
from .gmail_llm_prompt import (
    format_gmail_message_dict_for_llm_prompt,
    is_gmail_like_message_dict,
)
from .helpers import (
    _format_exception,
)
from .inputs import (
    _resolve_inputs_by_target_handle,
)


def _exec_skill_deps() -> Any:
    """Resolve ``executor`` at call time so tests can patch symbols on ``executor`` reliably."""
    import app.domain.workflow_executor.executor as executor_mod

    return executor_mod


def _error_with_resolved_inputs(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _exec_skill_deps()._error_with_resolved_inputs(*args, **kwargs)


def _error_with_structured(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _exec_skill_deps()._error_with_structured(*args, **kwargs)


class WorkflowExecutorSkillsRunnerMixin:
    async def _run_simple_llm_call_node(
        self,
        node: SimpleLLMCallSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve system_prompt and user_prompt from Persona (if persona_id set),
        or from required_inputs, overrides, or upstream.
        Call LMStudioProvider and return ResponseNodeOutput.
        """
        persona_id_raw = node.data.get("persona_id")
        persona: Optional[Persona] = None
        if persona_id_raw:
            try:
                pid = UUID(persona_id_raw) if isinstance(persona_id_raw, str) else persona_id_raw
            except (ValueError, TypeError):
                pid = None
            if pid is not None:
                async with self._async_session_lock:
                    persona = self.session.exec(
                        select(Persona)
                        .where(col(Persona.id) == pid)
                        .where(or_(col(Persona.user_id) == self.user_id, col(Persona.user_id).is_(None)))
                    ).first()

        if not persona:
            return {
                "status": "error",
                "error": (
                    f"Simple LLM Call node '{node.id}' requires a Persona. "
                    "Select a Persona in the Workflow Editor before running."
                ),
            }

        # Persona required: use its system_prompt, default_model, creativity
        # Resolve additional context from node field, upstream (handles additional_context or system_prompt), overrides
        additional_from_node = (node.data.get("additional_system_prompt_context") or "").strip()
        raw_inputs = node.data.get("required_inputs") or []
        resolved_addl = _resolve_inputs_by_target_handle(
            node.id, ["additional_context", "system_prompt"], edges, outputs, {}, raw_inputs
        )
        additional_from_upstream = (
            resolved_addl.get("additional_context") or resolved_addl.get("system_prompt") or ""
        ).strip()
        additional_from_overrides = (input_overrides.get("additional_system_prompt_context") or "").strip()

        if additional_from_overrides:
            additional_context = additional_from_overrides
        elif additional_from_node and additional_from_upstream:
            additional_context = additional_from_node + "\n\n" + additional_from_upstream
        elif additional_from_node:
            additional_context = additional_from_node
        elif additional_from_upstream:
            additional_context = additional_from_upstream
        else:
            additional_context = ""

        base_prompt = (persona.system_prompt or "You are a helpful assistant.").rstrip()
        addl_stripped = (additional_context or "").strip()
        if addl_stripped:
            core_system = f"{base_prompt}\n\n{addl_stripped}"
        else:
            core_system = base_prompt
        system_prompt = core_system
        model = persona.default_model
        creativity = persona.creativity

        # user_prompt resolved from required_inputs/overrides/upstream
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["user_prompt"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        user_prompt = resolved.get("user_prompt") or "Please proceed."
        if isinstance(user_prompt, dict) and is_gmail_like_message_dict(user_prompt):
            user_message_for_model = format_gmail_message_dict_for_llm_prompt(user_prompt)
            user_prompt = user_message_for_model
        else:
            user_message_for_model = str(user_prompt)

        # Resolve structure: structure_id on node OR upstream edge (target_handle="structure")
        schema_dict: Optional[Dict[str, Any]] = None
        structure_id_raw = node.data.get("structure_id")
        if structure_id_raw:
            try:
                sid = UUID(structure_id_raw) if isinstance(structure_id_raw, str) else structure_id_raw
            except (ValueError, TypeError):
                sid = None
            else:
                async with self._async_session_lock:
                    structure = self.session.exec(
                        select(Structure).where(
                            col(Structure.id) == sid,
                            or_(col(Structure.user_id) == self.user_id, col(Structure.user_id).is_(None)),
                        )
                    ).first()
                if structure:
                    try:
                        schema_dict = json.loads(structure.json_schema)
                    except json.JSONDecodeError:
                        pass
        if schema_dict is None:
            resolved_struct = _resolve_inputs_by_target_handle(
                node.id, ["structure"], edges, outputs, input_overrides, raw_inputs
            )
            schema_dict = (
                resolved_struct.get("structure") if isinstance(resolved_struct.get("structure"), dict) else None
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message_for_model},
        ]
        options: Dict[str, Any] = {"temperature": creativity}
        if model:
            options["model"] = model
        options.update(persona_lm_chat_options(persona))
        if schema_dict:
            normalized_schema = normalize_schema_for_structured_output(schema_dict)
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": normalized_schema,
                },
            }

        try:
            # Session is not safe for concurrent ORM use across parallel nodes; keep User read + decrypt
            # inside the same lock as other executor DB access. Refresh after enqueue commits the run row early
            # so api_keys is not a stale/expired in-memory JSON snapshot.
            async with self._async_session_lock:
                user_row = self.session.get(User, self.user_id)
                if user_row is not None:
                    self.session.refresh(user_row)
                decrypted_keys = decrypt_api_keys_store(user_row.api_keys if user_row else None)
                lm_token = resolve_lmstudio_bearer(decrypted_api_keys=decrypted_keys)
            provider = _exec_skill_deps().LMStudioProvider(api_key=lm_token)
            response = await provider.chat(messages, options=options)
        except Exception as e:
            return {"status": "error", "error": f"SimpleLLMCall failed: {_format_exception(e)}"}

        ri_llm: Dict[str, Any] = {
            "persona_system_prompt": base_prompt,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "additional_context": additional_context or "",
            "user_role_message": user_message_for_model,
            "model": model,
            "temperature": creativity,
            "suppress_lm_thinking": bool(getattr(persona, "suppress_lm_thinking", False)),
        }
        if schema_dict:
            ri_llm["structure_schema"] = schema_dict
        detail_common = {"resolved_inputs": ri_llm}

        if schema_dict and response.parsed is not None:
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=response.parsed),
                "details": detail_common,
            }
        return {
            "status": "ok",
            "output": ResponseNodeOutput(
                node_id=node.id,
                text=response.raw_text or "",
            ),
            "details": detail_common,
        }

    async def _run_multimodal_llm_call_node(
        self,
        node: MultimodalLLMCallSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persona + user prompt + image artifacts → LM Studio multimodal chat → ResponseNodeOutput."""
        persona_id_raw = node.data.get("persona_id")
        persona: Optional[Persona] = None
        if persona_id_raw:
            try:
                pid = UUID(persona_id_raw) if isinstance(persona_id_raw, str) else persona_id_raw
            except (ValueError, TypeError):
                pid = None
            if pid is not None:
                async with self._async_session_lock:
                    persona = self.session.exec(
                        select(Persona)
                        .where(col(Persona.id) == pid)
                        .where(or_(col(Persona.user_id) == self.user_id, col(Persona.user_id).is_(None)))
                    ).first()

        if not persona:
            return {
                "status": "error",
                "error": (
                    f"Multimodal LLM node '{node.id}' requires a Persona. "
                    "Select a Persona in the Workflow Editor before running."
                ),
            }

        additional_from_node = (node.data.get("additional_system_prompt_context") or "").strip()
        raw_inputs = node.data.get("required_inputs") or []
        resolved_addl = _resolve_inputs_by_target_handle(
            node.id, ["additional_context", "system_prompt"], edges, outputs, {}, raw_inputs
        )
        additional_from_upstream = (
            resolved_addl.get("additional_context") or resolved_addl.get("system_prompt") or ""
        ).strip()
        additional_from_overrides = (input_overrides.get("additional_system_prompt_context") or "").strip()

        if additional_from_overrides:
            additional_context = additional_from_overrides
        elif additional_from_node and additional_from_upstream:
            additional_context = additional_from_node + "\n\n" + additional_from_upstream
        elif additional_from_node:
            additional_context = additional_from_node
        elif additional_from_upstream:
            additional_context = additional_from_upstream
        else:
            additional_context = ""

        base_prompt = (persona.system_prompt or "You are a helpful assistant.").rstrip()
        addl_stripped = (additional_context or "").strip()
        if addl_stripped:
            core_system = f"{base_prompt}\n\n{addl_stripped}"
        else:
            core_system = base_prompt
        system_prompt = core_system
        model = persona.default_model
        mo = node.data.get("model")
        if isinstance(mo, str) and mo.strip():
            model = mo.strip()
        creativity = persona.creativity

        resolved_in = _resolve_inputs_by_target_handle(
            node.id,
            ["user_prompt", "prompt", "images"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        user_prompt = resolved_in.get("user_prompt") or resolved_in.get("prompt") or "Please proceed."
        if isinstance(user_prompt, dict) and is_gmail_like_message_dict(user_prompt):
            user_message_for_model = format_gmail_message_dict_for_llm_prompt(user_prompt)
            user_prompt = user_message_for_model
        else:
            user_message_for_model = str(user_prompt)

        images_raw = resolved_in.get("images")

        schema_dict: Optional[Dict[str, Any]] = None
        structure_id_raw = node.data.get("structure_id")
        if structure_id_raw:
            try:
                sid = UUID(structure_id_raw) if isinstance(structure_id_raw, str) else structure_id_raw
            except (ValueError, TypeError):
                sid = None
            else:
                async with self._async_session_lock:
                    structure = self.session.exec(
                        select(Structure).where(
                            col(Structure.id) == sid,
                            or_(col(Structure.user_id) == self.user_id, col(Structure.user_id).is_(None)),
                        )
                    ).first()
                if structure:
                    try:
                        schema_dict = json.loads(structure.json_schema)
                    except json.JSONDecodeError:
                        pass
        if schema_dict is None:
            resolved_struct = _resolve_inputs_by_target_handle(
                node.id, ["structure"], edges, outputs, input_overrides, raw_inputs
            )
            schema_dict = (
                resolved_struct.get("structure") if isinstance(resolved_struct.get("structure"), dict) else None
            )

        try:
            artifact_ids = normalize_images_input(images_raw)
        except MultimodalLLMInputError as e:
            return _error_with_structured(
                e.message,
                err_type=e.code,
                retryable=e.retryable,
                resolved={"images": images_raw, "user_prompt": user_prompt},
            )

        try:
            async with self._async_session_lock:
                image_parts = build_openai_image_parts_from_artifacts(self.session, self.user_id, artifact_ids)
        except MultimodalLLMInputError as e:
            return _error_with_structured(
                e.message,
                err_type=e.code,
                retryable=e.retryable,
                resolved={
                    "user_prompt": user_prompt,
                    "image_artifact_ids": image_artifact_refs_for_log(artifact_ids),
                },
            )

        user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_message_for_model}]
        user_content.extend(image_parts)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        options: Dict[str, Any] = {"temperature": creativity}
        if model:
            options["model"] = model
        options.update(persona_lm_chat_options(persona))
        if schema_dict:
            normalized_schema = normalize_schema_for_structured_output(schema_dict)
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": normalized_schema,
                },
            }

        try:
            async with self._async_session_lock:
                user_row = self.session.get(User, self.user_id)
                if user_row is not None:
                    self.session.refresh(user_row)
                decrypted_keys = decrypt_api_keys_store(user_row.api_keys if user_row else None)
                lm_token = resolve_lmstudio_bearer(decrypted_api_keys=decrypted_keys)
            provider = _exec_skill_deps().LMStudioProvider(api_key=lm_token)
            response = await provider.chat(messages, options=options)
        except LMStudioModelNotMultimodalError as e:
            ri_mm: Dict[str, Any] = {
                "persona_system_prompt": base_prompt,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "image_artifact_ids": image_artifact_refs_for_log(artifact_ids),
                "model": model,
                "temperature": creativity,
                "suppress_lm_thinking": bool(getattr(persona, "suppress_lm_thinking", False)),
            }
            if e.provider_detail:
                ri_mm["provider_detail"] = e.provider_detail
            return _error_with_structured(
                str(e),
                err_type="MODEL_NOT_MULTIMODAL",
                retryable=False,
                resolved=ri_mm,
            )
        except Exception as e:
            return {"status": "error", "error": f"MultimodalLLM failed: {_format_exception(e)}"}

        usage_meta: Dict[str, Any] = dict(response.usage) if isinstance(response.usage, dict) else {}
        md: Dict[str, Any] = {
            "model": model,
            "usage": usage_meta,
            "image_artifact_ids": image_artifact_refs_for_log(artifact_ids),
        }
        ri_llm: Dict[str, Any] = {
            "persona_system_prompt": base_prompt,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "additional_context": additional_context or "",
            "user_role_message": user_message_for_model,
            "model": model,
            "temperature": creativity,
            "suppress_lm_thinking": bool(getattr(persona, "suppress_lm_thinking", False)),
            "image_artifact_ids": image_artifact_refs_for_log(artifact_ids),
        }
        if schema_dict:
            ri_llm["structure_schema"] = schema_dict
        detail_common = {"resolved_inputs": ri_llm}

        if schema_dict and response.parsed is not None:
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=response.parsed),
                "details": detail_common,
            }
        return {
            "status": "ok",
            "output": ResponseNodeOutput(
                node_id=node.id,
                text=response.raw_text or "",
                metadata=md,
            ),
            "details": detail_common,
        }

    async def _run_text_to_speech_node(
        self,
        node: TextToSpeechSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_mid = node.data.get("tts_model_id")
        if not raw_mid:
            return _error_with_resolved_inputs(
                "Text-to-Speech requires a TTS model. Select one in the node inspector.",
                {"tts_model_id": None},
            )
        try:
            aid = UUID(str(raw_mid))
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": "Invalid tts_model_id",
                "details": {"resolved_inputs": {"tts_model_id": raw_mid}},
            }

        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["text"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        text_raw = resolved.get("text")
        if text_raw is None or str(text_raw).strip() == "":
            return _error_with_resolved_inputs(
                "Text-to-Speech requires non-empty text input.",
                {"text": text_raw},
            )
        text = str(text_raw).strip()

        opt_engine = (node.data.get("engine") or "").strip() or None
        tts_opts = node.data.get("tts_options")
        if tts_opts is None:
            tts_opts = {}
        elif not isinstance(tts_opts, dict):
            return {"status": "error", "error": "tts_options must be a JSON object", "details": {}}
        tts_opts = dict(tts_opts)

        voice_sample_id_resolved: Optional[str] = None
        raw_vsid = node.data.get("voice_sample_id")
        if raw_vsid is not None and str(raw_vsid).strip() != "":
            try:
                vsid = UUID(str(raw_vsid))
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "error": "Invalid voice_sample_id",
                    "details": {"resolved_inputs": {"voice_sample_id": raw_vsid}},
                }
            voice_sample_id_resolved = str(vsid)
            async with self._async_session_lock:
                sample = self.session.get(VoiceSample, vsid)
            if sample is None or sample.user_id != self.user_id:
                return _error_with_resolved_inputs(
                    "Unknown or inaccessible voice sample.",
                    {"voice_sample_id": voice_sample_id_resolved},
                )
            tts_opts["ref_audio_base64"] = base64.b64encode(sample.ref_audio).decode("ascii")
            tts_opts["ref_text"] = sample.ref_text
            if not (tts_opts.get("language") or "").strip():
                tts_opts["language"] = sample.language

        async with self._async_session_lock:
            art = self.session.get(TtsModelArtifact, aid)
        if art is None:
            return _error_with_resolved_inputs("Unknown TTS model id.", {"tts_model_id": str(aid)})
        if art.status != "ready" or not (art.local_key or "").strip():
            return _error_with_resolved_inputs(
                f"TTS model '{art.display_name}' is not ready (status={art.status}).",
                {"tts_model_id": str(aid), "status": art.status},
            )
        engine = art.engine
        if opt_engine and opt_engine != engine:
            return {
                "status": "error",
                "error": f"Node engine override {opt_engine!r} does not match registry engine {engine!r}.",
                "details": {"resolved_inputs": {"engine": opt_engine, "registry_engine": engine}},
            }

        try:
            wav = await _exec_skill_deps().synthesize_wav(engine, art.local_key, text, tts_opts)
        except TtsBridgeError as e:
            ri: Dict[str, Any] = {
                "user_prompt": text,
                "tts_model_id": str(aid),
                "engine": engine,
            }
            if voice_sample_id_resolved:
                ri["voice_sample_id"] = voice_sample_id_resolved
            return {
                "status": "error",
                "error": f"Text-to-Speech failed: {e}",
                "details": {"resolved_inputs": ri},
            }

        b64 = base64.b64encode(wav).decode("ascii")
        resolved_in: Dict[str, Any] = {
            "user_prompt": text,
            "tts_model_id": str(aid),
            "engine": engine,
            "display_name": art.display_name,
        }
        if voice_sample_id_resolved:
            resolved_in["voice_sample_id"] = voice_sample_id_resolved
        return {
            "status": "ok",
            "output": AudioNodeOutput(node_id=node.id, mime_type="audio/wav", audio_base64=b64),
            "details": {"resolved_inputs": resolved_in},
        }

    async def _run_transcribe_audio_node(
        self,
        node: TranscribeAudioSkillNode,
        node_id: str,
        *,
        stream_run_id: Optional[uuid.UUID],
        for_loop_id: Optional[str],
        for_loop_iteration: Optional[int],
    ) -> Dict[str, Any]:
        if stream_run_id is None:
            return {
                "status": "error",
                "error": "Voice input (transcribe_audio) must run in streaming mode from the editor.",
            }
        data = node.data or {}
        iter_n = 0 if for_loop_iteration is None else int(for_loop_iteration)
        key = TranscribeWaitKey(
            run_id=stream_run_id,
            node_id=node_id,
            for_loop_id=for_loop_id,
            iteration=iter_n,
        )
        try:
            fut = register_transcribe_wait(key)
        except RuntimeError as e:
            return {
                "status": "error",
                "error": str(e) or "Duplicate transcribe wait",
            }
        self._track_transcribe_wait(key)
        self._emit_interstitial(
            {
                "event": "input_required",
                "kind": "transcribe_audio",
                "run_id": str(stream_run_id),
                "node_id": node_id,
                "for_loop_id": for_loop_id,
                "for_loop_iteration": for_loop_iteration,
            }
        )
        try:
            audio_bytes = await asyncio.wait_for(fut, timeout=settings.STT_AUDIO_WAIT_TIMEOUT)
        except asyncio.CancelledError:
            cancel_transcribe_wait(key)
            raise
        except asyncio.TimeoutError:
            cancel_transcribe_wait(key)
            return {
                "status": "error",
                "error": "Timed out waiting for a recording. Use Talk, then Stop, to upload audio.",
            }
        finally:
            self._untrack_transcribe_wait(key)
        return await self._transcribe_audio_upload_to_string_output(
            node_id,
            data,
            audio_bytes,
            source_type="microphone",
            empty_error="Transcription was empty. Try a clearer recording.",
        )

    async def _run_audio_file_input_node(
        self,
        node: AudioFileInputSkillNode,
        node_id: str,
        *,
        stream_run_id: Optional[uuid.UUID],
        for_loop_id: Optional[str],
        for_loop_iteration: Optional[int],
    ) -> Dict[str, Any]:
        data = node.data or {}
        artifact_id_raw = data.get("audio_artifact_id")
        if isinstance(artifact_id_raw, str) and artifact_id_raw.strip():
            try:
                artifact_id = uuid.UUID(artifact_id_raw.strip())
            except ValueError:
                return {
                    "status": "error",
                    "error": "Audio File Input has an invalid saved file reference.",
                    "details": {"resolved_inputs": {"audio_artifact_id": artifact_id_raw}},
                }
            async with self._async_session_lock:
                artifact = self.session.get(AudioFileArtifact, artifact_id)
                if artifact is None or artifact.user_id != self.user_id:
                    artifact = None
                else:
                    artifact = AudioFileArtifact(
                        id=artifact.id,
                        user_id=artifact.user_id,
                        filename=artifact.filename,
                        mime_type=artifact.mime_type,
                        size_bytes=artifact.size_bytes,
                        audio_bytes=bytes(artifact.audio_bytes),
                        created_at=artifact.created_at,
                        updated_at=artifact.updated_at,
                    )
            if artifact is None:
                return {
                    "status": "error",
                    "error": "Audio file not found.",
                    "details": {"resolved_inputs": {"audio_artifact_id": str(artifact_id)}},
                }
            return await self._transcribe_audio_upload_to_string_output(
                node_id,
                data,
                TranscribeUpload(
                    data=artifact.audio_bytes,
                    filename=artifact.filename,
                    content_type=artifact.mime_type,
                ),
                source_type="audio_file",
                audio_artifact_id=str(artifact.id),
                empty_error="Transcript returned empty. Please try another audio file.",
            )

        if stream_run_id is None:
            return {
                "status": "error",
                "error": "Audio File Input needs a saved file or a streaming run-time file upload.",
            }

        iter_n = 0 if for_loop_iteration is None else int(for_loop_iteration)
        key = TranscribeWaitKey(
            run_id=stream_run_id,
            node_id=node_id,
            for_loop_id=for_loop_id,
            iteration=iter_n,
        )
        try:
            fut = register_transcribe_wait(key)
        except RuntimeError as e:
            return {
                "status": "error",
                "error": str(e) or "Duplicate audio file input wait",
            }
        self._track_transcribe_wait(key)
        self._emit_interstitial(
            {
                "event": "input_required",
                "kind": "audio_file_input",
                "run_id": str(stream_run_id),
                "node_id": node_id,
                "for_loop_id": for_loop_id,
                "for_loop_iteration": for_loop_iteration,
            }
        )
        try:
            audio_upload = await asyncio.wait_for(fut, timeout=settings.STT_AUDIO_WAIT_TIMEOUT)
        except asyncio.CancelledError:
            cancel_transcribe_wait(key)
            raise
        except asyncio.TimeoutError:
            cancel_transcribe_wait(key)
            return {
                "status": "error",
                "error": "Timed out waiting for an audio file upload.",
            }
        finally:
            self._untrack_transcribe_wait(key)
        return await self._transcribe_audio_upload_to_string_output(
            node_id,
            data,
            audio_upload,
            source_type="audio_file",
            empty_error="Transcript returned empty. Please try another audio file.",
        )

    async def _run_transcribe_file_node(
        self,
        node: TranscribeFileSkillNode,
        node_id: str,
        *,
        stream_run_id: Optional[uuid.UUID],
        for_loop_id: Optional[str],
        for_loop_iteration: Optional[int],
    ) -> Dict[str, Any]:
        """Run the provider-abstracted Transcribe File skill.

        See plan section 3 for the data-shape contract. The branches:

        1. Resolve audio bytes (saved artifact or runtime upload via input_required).
        2. Resolve the speech provider via the registry; resolve the API key from
           User.api_keys then env (mirrors LM Studio's bearer resolution).
        3. Persist a transcription_jobs row, call provider.submit, persist the result.
        4. For sync providers (local_whisper) the transcript is already in hand → emit.
        5. For async providers (assemblyai) poll inline with periodic heartbeats so the
           SSE client stays attached. On client cancel, the persisted row remains in a
           non-terminal state for the lifespan poller to advance.
        """
        # Imports kept inside the method so the executor doesn't pay their cost on every
        # graph evaluation (mirrors how other heavy paths in this module are structured).
        from app.domain.audio_file_validation import ValidatedAudioFile, safe_audio_filename
        from app.domain.services.audio_file_artifact_service import AudioFileArtifactService
        from app.domain.services.transcription_job_service import TranscriptionJobService

        data = node.data or {}
        provider_id_raw = data.get("provider")
        provider_id = (
            provider_id_raw.strip().lower()
            if isinstance(provider_id_raw, str) and provider_id_raw.strip()
            else "local_whisper"
        )

        # Refuse providers the deployment hasn't enabled (e.g. assemblyai with no key plan).
        enabled = enabled_provider_ids() or ["local_whisper"]
        if provider_id not in enabled:
            return _error_with_resolved_inputs(
                f"Transcribe File: provider {provider_id!r} is not enabled in this deployment "
                f"(allowed: {sorted(enabled)}).",
                {"provider": provider_id, "audio_artifact_id": data.get("audio_artifact_id")},
            )

        try:
            provider = _exec_skill_deps().get_speech_provider(provider_id)
        except TranscriptionProviderError as exc:
            return _error_with_resolved_inputs(
                f"Transcribe File: {exc}",
                {"provider": provider_id, "audio_artifact_id": data.get("audio_artifact_id")},
            )

        # ----- Build TranscriptionOptions from the node data -----
        task_raw = data.get("task")
        task_norm: str = "transcribe"
        if isinstance(task_raw, str) and task_raw.strip().lower() in ("transcribe", "translate"):
            task_norm = task_raw.strip().lower()
        language_raw = data.get("language")
        language = language_raw.strip() if isinstance(language_raw, str) and language_raw.strip() else None
        prompt_raw = data.get("prompt")
        prompt = prompt_raw.strip() if isinstance(prompt_raw, str) and prompt_raw.strip() else None
        diarization_enabled = bool(data.get("diarization_enabled"))
        include_word_timestamps = bool(data.get("include_word_timestamps"))
        pm_raw = data.get("provider_model_id")
        provider_model_id = pm_raw.strip() if isinstance(pm_raw, str) and pm_raw.strip() else None
        model_desc = tuple(type(provider).model_descriptors)
        if provider_model_id and model_desc:
            allowed = {m.id for m in model_desc}
            if provider_model_id not in allowed:
                return _error_with_resolved_inputs(
                    "Transcribe File: unknown speech model "
                    f"{provider_model_id!r} for provider {provider_id!r} "
                    f"(allowed: {sorted(allowed)}).",
                    {"provider": provider_id, "provider_model_id": provider_model_id},
                )
        try:
            options = TranscriptionOptions(
                language=language,
                diarization_enabled=diarization_enabled,
                include_word_timestamps=include_word_timestamps,
                prompt=prompt,
                task=task_norm,  # type: ignore[arg-type]
                provider_model_id=provider_model_id,
            )
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"Transcribe File: invalid options — {exc}",
                {"provider": provider_id},
            )

        # ----- Resolve audio bytes -----
        audio_artifact_id_raw = data.get("audio_artifact_id")
        artifact_path_used = isinstance(audio_artifact_id_raw, str) and bool(audio_artifact_id_raw.strip())

        artifact_id: Optional[uuid.UUID] = None
        audio_bytes: Optional[bytes] = None
        validated: Optional[ValidatedAudioFile] = None

        if artifact_path_used:
            raw_aid_local = audio_artifact_id_raw
            assert isinstance(raw_aid_local, str)
            try:
                artifact_id = uuid.UUID(raw_aid_local.strip())
            except ValueError:
                return _error_with_resolved_inputs(
                    "Transcribe File has an invalid saved file reference.",
                    {"provider": provider_id, "audio_artifact_id": audio_artifact_id_raw},
                )
            async with self._async_session_lock:
                row = self.session.get(AudioFileArtifact, artifact_id)
                if row is None or row.user_id != self.user_id:
                    return _error_with_resolved_inputs(
                        "Audio file not found.",
                        {"provider": provider_id, "audio_artifact_id": str(artifact_id)},
                    )
                audio_bytes = bytes(row.audio_bytes)
                validated = ValidatedAudioFile(
                    filename=row.filename,
                    mime_type=row.mime_type,
                    size_bytes=row.size_bytes,
                )
        else:
            if stream_run_id is None:
                return _error_with_resolved_inputs(
                    "Transcribe File needs a saved file or a streaming run-time file upload.",
                    {"provider": provider_id},
                )
            iter_n = 0 if for_loop_iteration is None else int(for_loop_iteration)
            wait_key = TranscribeWaitKey(
                run_id=stream_run_id,
                node_id=node_id,
                for_loop_id=for_loop_id,
                iteration=iter_n,
            )
            try:
                fut = register_transcribe_wait(wait_key)
            except RuntimeError as exc:
                return _error_with_resolved_inputs(
                    str(exc) or "Duplicate transcribe_file wait",
                    {"provider": provider_id},
                )
            self._track_transcribe_wait(wait_key)
            self._emit_interstitial(
                {
                    "event": "input_required",
                    "kind": "transcribe_file",
                    "run_id": str(stream_run_id),
                    "node_id": node_id,
                    "for_loop_id": for_loop_id,
                    "for_loop_iteration": for_loop_iteration,
                    "provider": provider_id,
                },
            )
            try:
                upload = await asyncio.wait_for(fut, timeout=settings.STT_AUDIO_WAIT_TIMEOUT)
            except asyncio.CancelledError:
                cancel_transcribe_wait(wait_key)
                raise
            except asyncio.TimeoutError:
                cancel_transcribe_wait(wait_key)
                return _error_with_resolved_inputs(
                    "Timed out waiting for an audio file upload.",
                    {"provider": provider_id},
                )
            finally:
                self._untrack_transcribe_wait(wait_key)

            audio_bytes = bytes(upload.data)
            validated = ValidatedAudioFile(
                filename=safe_audio_filename(upload.filename),
                mime_type=(upload.content_type or "application/octet-stream"),
                size_bytes=len(audio_bytes),
            )

            # Spill runtime upload to a transient AudioFileArtifact so the lifespan poller
            # (and any future restart) can re-read the bytes if the cloud job needs to be
            # resubmitted. Local Whisper is sync so we skip this spill there to avoid
            # paying the storage cost for a 100% successful inline call.
            if not provider.is_synchronous:
                artifact_service = AudioFileArtifactService(self.session, self.user_id)
                async with self._async_session_lock:
                    transient = artifact_service.create_transient(audio_bytes, validated)
                artifact_id = transient.id

        if not audio_bytes or len(audio_bytes) > settings.STT_MAX_AUDIO_UPLOAD_BYTES:
            return _error_with_resolved_inputs(
                "Invalid or too large audio payload",
                {
                    "provider": provider_id,
                    "audio_artifact_id": str(artifact_id) if artifact_id else None,
                    "size_bytes": len(audio_bytes) if audio_bytes else 0,
                },
            )

        assert validated is not None  # for mypy / readers — set by both branches above

        # ----- Resolve API key (only meaningful for non-local providers) -----
        api_key: Optional[str] = None
        if provider_id == "assemblyai":
            decrypted_keys = self._decrypted_user_api_keys()
            api_key = resolve_assemblyai_api_key(decrypted_keys)
            if not api_key:
                return _error_with_resolved_inputs(
                    "AssemblyAI provider selected but no API key found. "
                    "Add one in My Settings → API Settings, or set ASSEMBLYAI_API_KEY on the server.",
                    {"provider": provider_id},
                )

        # ----- Persist the row before the network call so a crash leaves a breadcrumb -----
        job_service = TranscriptionJobService(self.session, self.user_id)
        existing = job_service.find_existing_for_node(
            run_id=stream_run_id,
            node_id=node_id,
            for_loop_id=for_loop_id,
            for_loop_iteration=for_loop_iteration,
        )
        if existing is not None and existing.status == "completed" and existing.transcript_json:
            # Reattach idempotency: the previous executor already submitted+completed this
            # node (e.g., a poller advanced the row, the user re-ran the workflow with the
            # same artifact). Reuse the persisted transcript instead of re-uploading.
            primitive_dict = dict(existing.transcript_json)
            return self._build_transcribe_file_success(
                node_id=node_id,
                primitive_dict=primitive_dict,
                provider_id=provider_id,
                options=options,
                validated=validated,
                artifact_id=artifact_id,
            )

        if existing is not None:
            job_row = existing
        else:
            job_row = job_service.create_pending(
                run_id=stream_run_id,
                node_id=node_id,
                for_loop_id=for_loop_id,
                for_loop_iteration=for_loop_iteration,
                provider=provider_id,
                options=options,
                audio_artifact_id=artifact_id,
                validated_audio=validated,
            )

        # ----- Submit (idempotent if we already have a provider_job_id) -----
        try:
            if not job_row.provider_job_id:
                submission = await provider.submit(
                    audio=audio_bytes,
                    filename=validated.filename,
                    content_type=validated.mime_type,
                    options=options,
                    api_key=api_key,
                )
                job_row = job_service.apply_submission(job_row, submission)
        except TranscriptionProviderError as exc:
            job_service.mark_error(job_row, str(exc))
            job_service.cleanup_transient_audio(job_row)
            return _error_with_resolved_inputs(
                f"Transcription submit failed: {exc}",
                {
                    "provider": provider_id,
                    "audio_artifact_id": str(artifact_id) if artifact_id else None,
                    "transcribe_error": str(exc),
                },
            )
        except asyncio.CancelledError:
            # Submit was interrupted mid-flight; the row stays in 'submitting'. The poller
            # will advance it on the next pass (e.g. by retrying via the persisted bytes).
            raise

        # ----- Inline poll loop (sync providers short-circuit) -----
        if job_row.status == "completed" and job_row.transcript_json:
            primitive_dict = dict(job_row.transcript_json)
            job_service.cleanup_transient_audio(job_row)
            return self._build_transcribe_file_success(
                node_id=node_id,
                primitive_dict=primitive_dict,
                provider_id=provider_id,
                options=options,
                validated=validated,
                artifact_id=artifact_id,
            )

        if job_row.status == "error":
            err = job_row.provider_error or "Provider returned an error after submit."
            job_service.cleanup_transient_audio(job_row)
            return _error_with_resolved_inputs(
                f"Transcription failed: {err}",
                {
                    "provider": provider_id,
                    "audio_artifact_id": str(artifact_id) if artifact_id else None,
                    "transcribe_error": err,
                },
            )

        # Async path: poll until terminal or timeout.
        poll_interval = max(0.5, float(settings.ASSEMBLYAI_POLL_INTERVAL))
        job_timeout = max(poll_interval * 2, float(settings.ASSEMBLYAI_JOB_TIMEOUT))
        deadline = time.monotonic() + job_timeout
        provider_job_id = job_row.provider_job_id
        try:
            while True:
                if not provider_job_id:
                    job_service.mark_error(job_row, "Provider returned no job id.")
                    job_service.cleanup_transient_audio(job_row)
                    return _error_with_resolved_inputs(
                        "Transcription failed: provider returned no job id.",
                        {"provider": provider_id, "transcribe_error": "missing provider_job_id"},
                    )
                if time.monotonic() > deadline:
                    job_service.mark_error(
                        job_row,
                        f"Inline poll timed out after {int(job_timeout)}s; lifespan poller will continue.",
                    )
                    return _error_with_resolved_inputs(
                        "Transcription is still in progress; reattach to the run later to view the result.",
                        {
                            "provider": provider_id,
                            "transcription_job_id": str(job_row.id),
                            "provider_job_id": provider_job_id,
                            "audio_artifact_id": str(artifact_id) if artifact_id else None,
                        },
                    )
                await asyncio.sleep(poll_interval)
                if stream_run_id is not None:
                    self._emit_interstitial(
                        {
                            "event": "transcription_job_status",
                            "node_id": node_id,
                            "run_id": str(stream_run_id),
                            "provider": provider_id,
                            "status": job_row.status,
                            "provider_job_id": provider_job_id,
                            "transcription_job_id": str(job_row.id),
                        },
                    )
                try:
                    poll_result = await provider.poll(
                        provider_job_id=provider_job_id,
                        options=options,
                        api_key=api_key,
                    )
                except TranscriptionProviderError as exc:
                    if not exc.retryable:
                        job_service.mark_error(job_row, str(exc))
                        job_service.cleanup_transient_audio(job_row)
                        return _error_with_resolved_inputs(
                            f"Transcription poll failed: {exc}",
                            {
                                "provider": provider_id,
                                "transcribe_error": str(exc),
                                "transcription_job_id": str(job_row.id),
                            },
                        )
                    # Retryable provider error — keep looping; logger picks it up below.
                    logger.warning(
                        "transcribe_file retryable poll error provider=%s job=%s: %s",
                        provider_id,
                        provider_job_id,
                        exc,
                    )
                    continue
                job_row = job_service.apply_poll(job_row, poll_result)
                if job_row.status == "completed" and job_row.transcript_json:
                    primitive_dict = dict(job_row.transcript_json)
                    job_service.cleanup_transient_audio(job_row)
                    return self._build_transcribe_file_success(
                        node_id=node_id,
                        primitive_dict=primitive_dict,
                        provider_id=provider_id,
                        options=options,
                        validated=validated,
                        artifact_id=artifact_id,
                    )
                if job_row.status == "error":
                    err = job_row.provider_error or "Provider returned an error."
                    job_service.cleanup_transient_audio(job_row)
                    return _error_with_resolved_inputs(
                        f"Transcription failed: {err}",
                        {
                            "provider": provider_id,
                            "transcribe_error": err,
                            "transcription_job_id": str(job_row.id),
                        },
                    )
                if job_row.status == "cancelled":
                    return _error_with_resolved_inputs(
                        "Transcription was cancelled.",
                        {
                            "provider": provider_id,
                            "transcription_job_id": str(job_row.id),
                        },
                    )
        except asyncio.CancelledError:
            # Client disconnected. The row stays non-terminal so the lifespan poller takes over.
            raise

    def _decrypted_user_api_keys(self) -> Optional[Dict[str, Any]]:
        """Decrypt the running user's stored api_keys for provider key resolution."""
        from app.core.user_api_keys_crypto import decrypt_api_keys_store

        user = self.session.get(User, self.user_id)
        if user is None:
            return None
        try:
            return decrypt_api_keys_store(user.api_keys or {})
        except Exception:
            logger.exception("transcribe_file: failed to decrypt user api_keys")
            return None

    def _build_transcribe_file_success(
        self,
        *,
        node_id: str,
        primitive_dict: Dict[str, Any],
        provider_id: str,
        options: TranscriptionOptions,
        validated: ValidatedAudioFile,
        artifact_id: Optional[uuid.UUID],
    ) -> Dict[str, Any]:
        # Re-validate the dict so a stale/corrupt persisted blob can't poison the graph.
        from app.domain.schemas.transcript import TranscriptPrimitive

        try:
            primitive = TranscriptPrimitive.model_validate(primitive_dict)
        except Exception as exc:
            return _error_with_resolved_inputs(
                f"Transcribe File: persisted transcript failed validation — {exc}",
                {"provider": provider_id, "audio_artifact_id": str(artifact_id) if artifact_id else None},
            )
        primitive_data = primitive.model_dump(mode="json")
        resolved: Dict[str, Any] = {
            "provider": provider_id,
            "language": options.language,
            "task": options.task,
            "diarization_enabled": options.diarization_enabled,
            "include_word_timestamps": options.include_word_timestamps,
            "prompt": options.prompt,
            "filename": validated.filename,
            "mime_type": validated.mime_type,
            "size_bytes": validated.size_bytes,
            "audio_artifact_id": str(artifact_id) if artifact_id else None,
            "transcript_chars": len(primitive.full_text),
            "duration_seconds": primitive.duration_seconds,
        }
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node_id, data=primitive_data),
            "details": {
                "resolved_inputs": resolved,
                "transcript_segments_count": len(primitive.segments),
                "transcript_words_count": len(primitive.words),
            },
        }

    async def _transcribe_audio_upload_to_string_output(
        self,
        node_id: str,
        node_data: Dict[str, Any],
        audio_upload: TranscribeUpload,
        *,
        source_type: str,
        audio_artifact_id: Optional[str] = None,
        empty_error: str,
    ) -> Dict[str, Any]:
        task = (node_data.get("task") or "transcribe").strip().lower()
        if task not in ("transcribe", "translate"):
            task = "transcribe"
        lang = node_data.get("language")
        if isinstance(lang, str) and not lang.strip():
            lang = None
        elif isinstance(lang, str):
            lang = lang.strip() or None

        audio_bytes = audio_upload.data
        resolved_base: Dict[str, Any] = {
            "source_type": source_type,
            "filename": audio_upload.filename,
            "mime_type": audio_upload.content_type,
            "size_bytes": len(audio_bytes) if audio_bytes else 0,
            "task": task,
            "language": lang,
        }
        if audio_artifact_id:
            resolved_base["audio_artifact_id"] = audio_artifact_id

        if not audio_bytes or len(audio_bytes) > settings.STT_MAX_AUDIO_UPLOAD_BYTES:
            return {
                "status": "error",
                "error": "Invalid or too large audio payload",
                "details": {"resolved_inputs": resolved_base},
            }
        try:
            logger.info(
                "stt transcription starting node_id=%s source_type=%s bytes=%s filename=%s",
                node_id,
                source_type,
                len(audio_bytes),
                audio_upload.filename,
            )
            payload = await _exec_skill_deps().transcribe_audio_bytes(
                bytes(audio_bytes),
                task=task,
                language=lang,
                filename=audio_upload.filename,
                content_type=audio_upload.content_type,
            )
            logger.info("stt transcription completed node_id=%s source_type=%s", node_id, source_type)
        except SttBridgeHttpError as e:
            resolved = dict(resolved_base)
            resolved["transcribe_error"] = str(e)
            return {
                "status": "error",
                "error": f"Transcription failed: {e}",
                "details": {"resolved_inputs": resolved},
            }
        text = (payload.get("text") or "").strip() if isinstance(payload, dict) else ""
        if not text:
            return {
                "status": "error",
                "error": empty_error,
                "details": {"resolved_inputs": resolved_base},
            }
        segments = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(segments, list):
            segments = []
        tlang = payload.get("language") if isinstance(payload, dict) else None
        duration_seconds = None
        if isinstance(payload, dict) and payload.get("duration_seconds") is not None:
            try:
                duration_seconds = float(payload["duration_seconds"])
            except (TypeError, ValueError):
                duration_seconds = None
        resolved = dict(resolved_base)
        resolved.update(
            {
                "transcribe_language": tlang,
                "transcript_chars": len(text),
            }
        )
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node_id, text=text),
            "details": {
                "resolved_inputs": resolved,
                "transcribe_segments": segments,
                "duration_seconds": duration_seconds,
            },
        }

    @staticmethod
    def _coerce_int_cap(val: Any, default: int, cap: int) -> int:
        try:
            if val is None:
                return default
            n = int(val)
            if n < 1:
                return default
            return min(n, cap)
        except (TypeError, ValueError):
            return default

    async def _run_gmail_list_messages_node(
        self,
        node: GmailListMessagesSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        execution_time_zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn_row = get_user_workflow_google_connection(self.session, self.user_id)
        if conn_row is None:
            return _error_with_resolved_inputs(
                GOOGLE_WORKFLOW_CONNECTION_REQUIRED_MSG,
                {"google_connection_id": None},
            )
        conn_uuid = conn_row.id

        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["after", "before", "unread_only", "query", "max_results"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        query_val = resolved.get("query")
        if query_val is None or str(query_val).strip() == "":
            q_inline = node.data.get("query")
            query_val = q_inline
        raw_q: Optional[str]
        if query_val is None or str(query_val).strip() == "":
            raw_q = None
        else:
            raw_q = str(query_val).strip()

        after_val = resolved.get("after")
        if after_val is None or str(after_val).strip() == "":
            after_s = node.data.get("after")
            after_rfc3339 = str(after_s).strip() if after_s else None
        else:
            after_rfc3339 = str(after_val).strip()

        before_val = resolved.get("before")
        if before_val is None or str(before_val).strip() == "":
            before_s = node.data.get("before")
            before_rfc3339 = str(before_s).strip() if before_s else None
        else:
            before_rfc3339 = str(before_val).strip()

        unread_resolved = resolved.get("unread_only")
        if unread_resolved is None:
            unread_only = coerce_bool_unread(node.data.get("unread_only"))
        else:
            unread_only = coerce_bool_unread(unread_resolved)

        if not after_rfc3339:
            after_rfc3339 = None
        if not before_rfc3339:
            before_rfc3339 = None

        user_row = self.session.get(User, self.user_id)
        acct: Dict[str, Any] = dict(user_row.settings or {}) if user_row else {}
        gmail_list_calendar_zone = _exec_skill_deps()._effective_gmail_calendar_zone(acct, execution_time_zone)

        try:
            base_q = build_messages_list_q(
                raw_query=raw_q,
                after_rfc3339=after_rfc3339,
                before_rfc3339=before_rfc3339,
                unread_only=unread_only,
                gmail_list_calendar_zone=gmail_list_calendar_zone,
            )
        except ValueError as e:
            return {
                "status": "error",
                "error": f"Invalid Gmail time filter: {e}",
                "details": {
                    "resolved_inputs": {
                        "google_connection_id": str(conn_uuid),
                        "after": after_rfc3339,
                        "before": before_rfc3339,
                        "unread_only": unread_only,
                        "query": raw_q,
                        "gmail_list_calendar_zone": gmail_list_calendar_zone,
                    }
                },
            }
        skip_acct = coerce_bool_unread(node.data.get("gmail_skip_account_category_filters"))

        if "gmail_inbox_focus" in node.data:
            eff_focus = normalize_gmail_inbox_focus(node.data.get("gmail_inbox_focus"))
        elif not skip_acct:
            eff_focus = normalize_gmail_inbox_focus(acct.get("gmail_workflow_inbox_focus"))
        else:
            eff_focus = "off"

        if "gmail_exclude_categories" in node.data:
            eff_exclude = normalize_gmail_exclude_categories(node.data.get("gmail_exclude_categories"))
        elif not skip_acct:
            eff_exclude = normalize_gmail_exclude_categories(acct.get("gmail_workflow_exclude_categories"))
        else:
            eff_exclude = []

        final_q = append_category_q_clauses(
            base_q,
            inbox_focus=eff_focus,
            exclude_categories=eff_exclude,
        )

        mr_default = self._coerce_int_cap(node.data.get("max_results"), 10, 100)
        max_results = self._coerce_int_cap(resolved.get("max_results"), mr_default, 100)

        gmail_ri: Dict[str, Any] = {
            "google_connection_id": str(conn_uuid),
            "after": after_rfc3339,
            "before": before_rfc3339,
            "unread_only": unread_only,
            "query": raw_q,
            "max_results": max_results,
            "gmail_inbox_focus": eff_focus,
            "gmail_exclude_categories": eff_exclude,
            "gmail_skip_account_category_filters": skip_acct,
            "q": final_q,
            "gmail_list_calendar_zone": gmail_list_calendar_zone,
        }

        try:
            ex = _exec_skill_deps()
            access = await ex.ensure_workflow_google_access_token(self.session, conn_uuid, self.user_id)
            raw = await ex.gmail_list_messages(
                access,
                max_results=max_results,
                query=final_q,
            )
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e),
                "details": {"resolved_inputs": gmail_ri},
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"GmailListMessages failed: {_format_exception(e)}",
                "details": {"resolved_inputs": gmail_ri},
            }

        messages = raw.get("messages") or []
        safe_list: List[Dict[str, Any]] = []
        list_refs = [m for m in messages if isinstance(m, dict)]
        attempted = sum(1 for m in list_refs if isinstance(m.get("id"), str) and str(m.get("id")).strip() != "")
        if list_refs:
            sem = asyncio.Semaphore(6)

            async def _fetch_one(ref: dict[str, Any]) -> Dict[str, Any]:
                mid = ref.get("id")
                tid = ref.get("threadId")
                if not isinstance(mid, str) or not mid.strip():
                    return {}
                mid_s = mid.strip()
                async with sem:
                    try:
                        full = await _exec_skill_deps().gmail_get_message_full(access, mid_s)
                        return curated_gmail_message_from_full_api(
                            full,
                            max_body_chars=GMAIL_MESSAGE_BODY_MAX_CHARS,
                        )
                    except Exception as e:
                        err = _format_exception(e)[:500]
                        err_item: Dict[str, Any] = {"id": mid_s, "fetch_error": err}
                        if isinstance(tid, str) and tid.strip():
                            err_item["threadId"] = tid.strip()
                        return err_item

            parts = await asyncio.gather(*[_fetch_one(m) for m in list_refs])
            safe_list = [p for p in parts if p]

        ok_count = sum(1 for x in safe_list if "fetch_error" not in x)
        failed_count = sum(1 for x in safe_list if "fetch_error" in x)

        diag_response, diag_truncated, diag_omitted = truncate_gmail_messages_list_response(raw)
        diag_payload: Dict[str, Any] = {
            "operation": "users.messages.list",
            "q": final_q,
            "gmail_category_filters": {
                "effective_inbox_focus": eff_focus,
                "effective_exclude_categories": eff_exclude,
                "skip_account_category_filters": skip_acct,
            },
            "response": diag_response,
            "truncated": diag_truncated,
            "omitted_message_count": diag_omitted,
            "message_gets": {
                "attempted": attempted,
                "ok": ok_count,
                "failed": failed_count,
            },
        }
        details = merge_skill_diagnostics(
            {
                "message_count": len(safe_list),
                "resolved_inputs": gmail_ri,
                "gmail_result_size_estimate": raw.get("resultSizeEstimate"),
            },
            vendor_key="gmail_v1",
            payload=diag_payload,
        )
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=safe_list),
            "details": details,
        }

    async def _run_calendar_list_events_node(
        self,
        node: CalendarListEventsSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        conn_row = get_user_workflow_google_connection(self.session, self.user_id)
        if conn_row is None:
            return _error_with_resolved_inputs(
                GOOGLE_WORKFLOW_CONNECTION_REQUIRED_MSG,
                {"google_connection_id": None},
            )
        conn_uuid = conn_row.id

        cal_raw = node.data.get("calendar_id")
        calendar_id = (str(cal_raw).strip() if cal_raw else "") or "primary"

        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["time_min", "time_max"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        time_min = resolved.get("time_min") or node.data.get("time_min")
        time_max = resolved.get("time_max") or node.data.get("time_max")
        if not time_min or not time_max:
            return {
                "status": "error",
                "error": "Calendar List Events requires time_min and time_max (RFC3339, e.g. 2026-03-01T00:00:00Z).",
                "details": {
                    "resolved_inputs": {
                        "google_connection_id": str(conn_uuid),
                        "calendar_id": calendar_id,
                        "time_min": time_min,
                        "time_max": time_max,
                    }
                },
            }
        t_min = str(time_min).strip()
        t_max = str(time_max).strip()

        calendar_ri: Dict[str, Any] = {
            "google_connection_id": str(conn_uuid),
            "calendar_id": calendar_id,
            "time_min": t_min,
            "time_max": t_max,
        }

        try:
            ex = _exec_skill_deps()
            access = await ex.ensure_workflow_google_access_token(self.session, conn_uuid, self.user_id)
            raw = await ex.calendar_list_events(access, calendar_id, time_min=t_min, time_max=t_max)
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e),
                "details": {"resolved_inputs": calendar_ri},
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"CalendarListEvents failed: {_format_exception(e)}",
                "details": {"resolved_inputs": calendar_ri},
            }

        events = raw.get("items") or []
        curated: List[Dict[str, Any]] = []
        if isinstance(events, list):
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                curated.append(curated_google_calendar_event(ev))

        diag_response, diag_truncated, diag_omitted = truncate_google_calendar_events_list_response(raw)
        diag_payload: Dict[str, Any] = {
            "operation": "events.list",
            "response": diag_response,
            "truncated": diag_truncated,
            "omitted_event_count": diag_omitted,
        }
        details = merge_skill_diagnostics(
            {"event_count": len(curated), "resolved_inputs": calendar_ri},
            vendor_key="google_calendar_v3",
            payload=diag_payload,
        )

        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data={"events": curated}),
            "details": details,
        }

    async def _run_google_docs_get_document_node(
        self,
        node: GoogleDocsGetDocumentSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        conn_row = get_user_workflow_google_connection(self.session, self.user_id)
        if conn_row is None:
            return _error_with_resolved_inputs(
                GOOGLE_WORKFLOW_CONNECTION_REQUIRED_MSG,
                {"google_connection_id": None},
            )
        conn_uuid = conn_row.id

        raw_inputs = node.data.get("required_inputs") or [
            {"key": "document_url_or_id", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["document_url_or_id"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        url_or_id = resolved.get("document_url_or_id") or node.data.get("document_url_or_id")
        if url_or_id is None or not str(url_or_id).strip():
            return _error_with_resolved_inputs(
                "Google Docs Get Document requires a document URL or ID.",
                {
                    "google_connection_id": str(conn_uuid),
                    "document_url_or_id": url_or_id,
                },
            )
        url_or_id_s = str(url_or_id).strip()
        try:
            document_id = parse_google_docs_url_or_id(url_or_id_s)
        except GoogleDocsUrlParseError as e:
            return _error_with_resolved_inputs(
                str(e),
                {
                    "google_connection_id": str(conn_uuid),
                    "document_url_or_id": url_or_id_s,
                },
            )

        include_tabs = node.data.get("include_tabs_content")
        if include_tabs is None:
            include_tabs_content = True
        else:
            include_tabs_content = bool(include_tabs)

        docs_ri: Dict[str, Any] = {
            "google_connection_id": str(conn_uuid),
            "document_url_or_id": url_or_id_s,
            "document_id": document_id,
            "include_tabs_content": include_tabs_content,
        }

        try:
            ex = _exec_skill_deps()
            access = await ex.ensure_workflow_google_access_token(self.session, conn_uuid, self.user_id)
            raw = await ex.docs_get_document(
                access,
                document_id,
                include_tabs_content=include_tabs_content,
            )
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e),
                "details": {"resolved_inputs": docs_ri},
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"GoogleDocsGetDocument failed: {_format_exception(e)}",
                "details": {"resolved_inputs": docs_ri},
            }

        try:
            document_payload, _fetch_errors = await build_document_payload(
                self.session,
                self.user_id,
                access,
                raw,
                document_id=document_id,
            )
            self.session.commit()
        except Exception as e:
            return {
                "status": "error",
                "error": f"GoogleDocsGetDocument curation failed: {_format_exception(e)}",
                "details": {"resolved_inputs": docs_ri},
            }

        diag_response, diag_truncated = truncate_google_docs_get_response(raw)
        diag_payload: Dict[str, Any] = {
            "operation": "documents.get",
            "document_id": document_id,
            "response": diag_response,
            "truncated": diag_truncated,
            "image_count": document_payload.get("image_count"),
            "fetch_error_count": len(document_payload.get("fetch_errors") or []),
        }
        details = merge_skill_diagnostics(
            {
                "resolved_inputs": docs_ri,
                "tab_count": document_payload.get("tab_count"),
                "image_count": document_payload.get("image_count"),
            },
            vendor_key="google_docs_v1",
            payload=diag_payload,
        )

        return {
            "status": "ok",
            "output": DictionaryNodeOutput(
                node_id=node.id,
                data={"document_payload": document_payload},
            ),
            "details": details,
        }

    async def _run_fetch_url_node(
        self,
        node: FetchUrlSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["url"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        url_val = resolved.get("url")
        if url_val is None or (isinstance(url_val, str) and str(url_val).strip() == ""):
            u_inline = node.data.get("url")
            url_val = u_inline
        url_s = str(url_val).strip() if url_val is not None else ""

        method_raw = node.data.get("method") or "GET"
        method_s = str(method_raw).upper().strip()

        h_raw = node.data.get("headers")
        hdrs = normalize_headers(h_raw)

        timeout_ms = node.data.get("timeout_ms")
        to_ms: Optional[int] = None
        if timeout_ms is not None:
            try:
                to_ms = int(timeout_ms)
            except (TypeError, ValueError):
                to_ms = None

        policy_raw = node.data.get("cache_policy") or "default"
        policy = str(policy_raw).lower().strip()
        if policy not in ("default", "refresh", "bypass"):
            policy = "default"

        ri: Dict[str, Any] = {
            "url": url_s,
            "method": method_s,
            "header_keys": sorted(hdrs.keys()),
            "timeout_ms": to_ms,
            "cache_policy": policy,
        }

        cache_key = compute_cache_key(url_s, method_s, hdrs)

        if policy == "default" and url_s:
            hit = get_cached_payload(self.session, self.user_id, cache_key)
            if hit is not None:
                return {
                    "status": "ok",
                    "output": DictionaryNodeOutput(node_id=node.id, data=hit),
                    "details": {"resolved_inputs": ri},
                }

        out = await _exec_skill_deps().perform_http_fetch(
            url=url_s,
            method=method_s,
            headers=hdrs,
            timeout_ms=to_ms,
            max_body_bytes=settings.FETCH_URL_MAX_BODY_BYTES,
        )

        cacheable = "error" not in out and "status_code" in out
        if cacheable and policy in ("default", "refresh"):
            upsert_success_cache(self.session, self.user_id, cache_key, out)

        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=out),
            "details": {"resolved_inputs": ri},
        }

    async def _run_capture_url_snapshot_node(
        self,
        node: CaptureUrlSnapshotSkillNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["url"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        url_val = resolved.get("url")
        if url_val is None or (isinstance(url_val, str) and str(url_val).strip() == ""):
            u_inline = node.data.get("url")
            url_val = u_inline
        url_s = str(url_val).strip() if url_val is not None else ""

        fp_raw = node.data.get("full_page")
        if fp_raw is None:
            full_page = True
        else:
            full_page = (
                bool(fp_raw)
                if not isinstance(fp_raw, str)
                else str(fp_raw).strip().lower()
                in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
            )

        vw = node.data.get("viewport_width")
        vh = node.data.get("viewport_height")
        try:
            viewport_w = int(vw) if vw is not None else settings.CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_WIDTH
        except (TypeError, ValueError):
            viewport_w = settings.CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_WIDTH
        try:
            viewport_h = int(vh) if vh is not None else settings.CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_HEIGHT
        except (TypeError, ValueError):
            viewport_h = settings.CAPTURE_URL_SNAPSHOT_DEFAULT_VIEWPORT_HEIGHT

        wu = str(node.data.get("wait_until") or "load").lower().strip()
        if wu not in ("load", "domcontentloaded", "networkidle"):
            wu = "load"

        timeout_ms = node.data.get("timeout_ms")
        to_ms: Optional[int] = None
        if timeout_ms is not None:
            try:
                to_ms = int(timeout_ms)
            except (TypeError, ValueError):
                to_ms = None
        if to_ms is None or to_ms < 1:
            to_ms = settings.CAPTURE_URL_SNAPSHOT_DEFAULT_TIMEOUT_MS

        policy_raw = node.data.get("cache_policy") or "default"
        policy = str(policy_raw).lower().strip()
        if policy not in ("default", "refresh", "bypass"):
            policy = "default"

        ri: Dict[str, Any] = {
            "url": url_s,
            "full_page": full_page,
            "viewport_width": viewport_w,
            "viewport_height": viewport_h,
            "wait_until": wu,
            "timeout_ms": to_ms,
            "cache_policy": policy,
        }

        ckey = compute_snapshot_cache_key(
            url_s,
            full_page=full_page,
            viewport_w=viewport_w,
            viewport_h=viewport_h,
            wait_until=wu,
        )

        if policy == "default" and url_s:
            hit = get_cache_artifact(self.session, self.user_id, ckey)
            if hit is not None:
                cap = hit.updated_at
                if cap is not None and cap.tzinfo is None:
                    cap = cap.replace(tzinfo=timezone.utc)
                captured_s = cap.isoformat().replace("+00:00", "Z") if cap is not None else ""
                fu = (getattr(hit, "final_url", None) or "").strip() or url_s
                return {
                    "status": "ok",
                    "output": DictionaryNodeOutput(
                        node_id=node.id,
                        data=build_success_output_from_artifact(
                            artifact_id=str(hit.id),
                            width=hit.width,
                            height=hit.height,
                            final_url=fu,
                            captured_at=captured_s,
                            duration_ms=0,
                            cached=True,
                        ),
                    ),
                    "details": {"resolved_inputs": ri},
                }

        # refresh / bypass / miss: capture (bypass and refresh skip cache read — handled above for default)
        raw = await _exec_skill_deps().perform_url_snapshot_capture(
            url=url_s,
            full_page=full_page,
            viewport_width=viewport_w,
            viewport_height=viewport_h,
            wait_until=wu,
            timeout_ms=to_ms,
            max_png_bytes=settings.CAPTURE_URL_SNAPSHOT_MAX_PNG_BYTES,
        )
        if "error" in raw:
            out = strip_internal_keys_for_output(raw)
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=out),
                "details": {"resolved_inputs": ri},
            }

        b = raw.get("_png_bytes")
        if not isinstance(b, (bytes, bytearray)):
            out = {
                "error": {
                    "type": "SCREENSHOT",
                    "message": "Internal capture result missing image bytes",
                    "retryable": True,
                },
                "captured_at": raw.get("captured_at", ""),
                "duration_ms": int(raw.get("duration_ms", 0)),
                "cached": False,
            }
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=out),
                "details": {"resolved_inputs": ri},
            }

        resolved_final_url = str(raw.get("final_url", url_s))
        art = create_artifact(
            self.session,
            self.user_id,
            bytes(b),
            int(raw["_width"]),
            int(raw["_height"]),
            final_url=resolved_final_url,
        )
        if policy in ("default", "refresh"):
            upsert_cache(self.session, self.user_id, ckey, art)

        data_out = build_success_output_from_artifact(
            artifact_id=str(art.id),
            width=art.width,
            height=art.height,
            final_url=resolved_final_url,
            captured_at=str(raw.get("captured_at", "")),
            duration_ms=int(raw.get("duration_ms", 0)),
            cached=False,
        )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data_out),
            "details": {"resolved_inputs": ri},
        }
