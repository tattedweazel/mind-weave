"""Re-export NDJSON-compat helpers; canonical module is ``app.domain.workflow_sse_ndjson_compat``."""

from app.domain.workflow_sse_ndjson_compat import iter_sse_pairs_as_ndjson, sse_tuple_to_ndjson_like_event

__all__ = ["iter_sse_pairs_as_ndjson", "sse_tuple_to_ndjson_like_event"]
