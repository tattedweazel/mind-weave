import { ExternalLink } from './ExternalLink';

/**
 * Body for ContextHelpModal: Persona "Suppress extended thinking" (LM Studio).
 */
export function PersonaSuppressThinkingHelpContent() {
    return (
        <div className="space-y-3 text-mw-text-primary">
            <p>
                When enabled, Mind Weave adds <code className="font-mono bg-mw-card-alt px-1 rounded">reasoning_effort: &quot;none&quot;</code> to{' '}
                <strong>OpenAI-compatible</strong> <code className="font-mono bg-mw-card-alt px-1 rounded">POST …/v1/chat/completions</code> requests for this Persona (workspace
                chat and workflow <strong>Simple LLM Call</strong> steps that use this Persona).
            </p>
            <p>
                <strong>LM Studio 0.4.8+</strong> documents this parameter on the compatible API. Older builds may ignore unknown fields.
            </p>
            <p>
                Use this when a <strong>thinking-capable</strong> local model misbehaves with extended reasoning but still works well without it. Models that do not use reasoning
                typically ignore the flag.
            </p>
            <p>
                <ExternalLink href="https://lmstudio.ai/changelog/lmstudio-v0.4.8">LM Studio 0.4.8 release notes</ExternalLink>
            </p>
        </div>
    );
}
