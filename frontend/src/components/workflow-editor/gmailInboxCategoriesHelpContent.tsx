/**
 * Help copy for Gmail List **Inbox categories** (moved from inline inspector text).
 */

export function GmailInboxCategoriesHelpContent() {
    return (
        <div className="space-y-3 text-mw-text-primary">
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                Gmail tab labels (e.g.{' '}
                <code className="font-mono text-[10px] text-mw-text-primary">CATEGORY_PROMOTIONS</code>) map to search
                clauses. Defaults come from <strong className="text-mw-text-primary">My Settings → Google</strong> unless you
                customize here or use <strong className="text-mw-text-primary">Skip account category filters</strong>.
            </p>
            <p className="text-mw-text-secondary text-[11px] leading-relaxed">
                Category filters are combined with <strong className="text-mw-text-primary">After</strong>,{' '}
                <strong className="text-mw-text-primary">Before</strong>,{' '}
                <strong className="text-mw-text-primary">Unread only</strong>, and{' '}
                <strong className="text-mw-text-primary">Search query</strong> into one{' '}
                <code className="font-mono text-[10px]">q</code>. Inspect the final string in{' '}
                <strong className="text-mw-text-primary">Last Run</strong> diagnostics (
                <strong className="text-mw-text-primary">Skill diagnostics</strong>).
            </p>
        </div>
    );
}
