import { ExternalLink } from '../ExternalLink';

const LINK_SEARCH = 'https://support.google.com/mail/answer/7190';
const LINK_API = 'https://developers.google.com/gmail/api/reference/rest/v1/users.messages/list';

/**
 * Concise primer for Gmail `q` (users.messages.list) shown in the workflow inspector.
 */
export function GmailQueryHelpContent() {
    return (
        <div className="space-y-3 text-mw-text-primary">
            <p className="text-mw-text-secondary leading-relaxed">
                This field uses the same operators as the Gmail search box. The node also adds{' '}
                <strong className="text-mw-text-primary">After</strong>, <strong className="text-mw-text-primary">Before</strong>, and{' '}
                <strong className="text-mw-text-primary">Unread only</strong> into the same query automatically—space-separated (AND).
            </p>
            <p className="text-amber-800 dark:text-amber-200/90 text-[11px] leading-snug">
                Avoid conflicts (e.g. typing <code className="font-mono text-[10px]">is:read</code> here while <strong>Unread only</strong> is
                checked).
            </p>
            <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary mb-1">Common operators</div>
                <ul className="list-disc list-inside space-y-0.5 text-mw-text-secondary marker:text-mw-text-secondary">
                    <li>
                        <code className="font-mono text-mw-text-primary">from:user@domain.com</code> /{' '}
                        <code className="font-mono text-mw-text-primary">to:…</code>
                    </li>
                    <li>
                        <code className="font-mono text-mw-text-primary">subject:word</code>
                    </li>
                    <li>
                        <code className="font-mono text-mw-text-primary">has:attachment</code>
                    </li>
                    <li>
                        <code className="font-mono text-mw-text-primary">in:inbox</code>,{' '}
                        <code className="font-mono text-mw-text-primary">is:starred</code>,{' '}
                        <code className="font-mono text-mw-text-primary">category:primary</code>,{' '}
                        <code className="font-mono text-mw-text-primary">-category:promotions</code> (exclude tab)
                    </li>
                    <li>
                        Inbox tab categories (see Google&apos;s docs):{' '}
                        <code className="font-mono text-mw-text-primary">primary</code>,{' '}
                        <code className="font-mono text-mw-text-primary">social</code>,{' '}
                        <code className="font-mono text-mw-text-primary">promotions</code>,{' '}
                        <code className="font-mono text-mw-text-primary">updates</code>,{' '}
                        <code className="font-mono text-mw-text-primary">forums</code>,{' '}
                        <code className="font-mono text-mw-text-primary">reservations</code>,{' '}
                        <code className="font-mono text-mw-text-primary">purchases</code>. Message{' '}
                        <code className="font-mono text-mw-text-primary">labelIds</code> uses names like{' '}
                        <code className="font-mono text-mw-text-primary">CATEGORY_PROMOTIONS</code>.
                    </li>
                    <li>
                        Relative time in raw query: <code className="font-mono text-mw-text-primary">newer_than:7d</code>,{' '}
                        <code className="font-mono text-mw-text-primary">older_than:1m</code> (see Google&apos;s docs for units)
                    </li>
                </ul>
            </div>
            <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-mw-text-secondary mb-1">Examples</div>
                <pre className="text-[11px] font-mono bg-mw-card-alt border border-mw-border rounded-lg p-2 overflow-x-auto whitespace-pre-wrap text-mw-text-primary">
                    {`from:alice@company.com newer_than:30d
has:attachment subject:invoice
in:inbox is:starred
is:unread -category:promotions`}
                </pre>
            </div>
            <p className="text-[11px] text-mw-text-secondary">
                <ExternalLink href={LINK_SEARCH} className="text-mw-primary hover:underline">
                    Gmail search operators
                </ExternalLink>
                {' · '}
                <ExternalLink href={LINK_API} className="text-mw-primary hover:underline">
                    API <code className="text-[10px]">q</code> parameter
                </ExternalLink>
            </p>
        </div>
    );
}
