/**
 * Gmail inbox category / tab filters for workflow `q` (aligned with backend gmail_query.py).
 */

export const GMAIL_EXCLUDABLE_CATEGORY_SLUGS = [
    'promotions',
    'social',
    'updates',
    'forums',
    'reservations',
    'purchases',
] as const;

export type GmailExcludableCategory = (typeof GMAIL_EXCLUDABLE_CATEGORY_SLUGS)[number];

export type GmailInboxFocus = 'off' | 'primary';

const FOCUS: ReadonlySet<string> = new Set(['off', 'primary']);

export function normalizeGmailInboxFocus(raw: unknown): GmailInboxFocus {
    if (raw == null || typeof raw !== 'string') return 'off';
    const s = raw.trim().toLowerCase();
    return FOCUS.has(s) ? (s as GmailInboxFocus) : 'off';
}

export function normalizeGmailExcludeCategories(raw: unknown): GmailExcludableCategory[] {
    if (raw == null || !Array.isArray(raw)) return [];
    const allow = new Set<string>(GMAIL_EXCLUDABLE_CATEGORY_SLUGS);
    const seen = new Set<string>();
    const out: GmailExcludableCategory[] = [];
    for (const item of raw) {
        if (typeof item !== 'string') continue;
        const slug = item.trim().toLowerCase();
        if (!allow.has(slug) || seen.has(slug)) continue;
        seen.add(slug);
        out.push(slug as GmailExcludableCategory);
    }
    return out;
}

/** Category-only fragment(s) appended after base `q` (no leading space). */
export function describeGmailCategoryClauses(inboxFocus: string, excludeCategories: string[]): string {
    const focus = normalizeGmailInboxFocus(inboxFocus);
    if (focus === 'primary') return 'category:primary';
    const ex = normalizeGmailExcludeCategories(excludeCategories);
    if (ex.length === 0) return '';
    return ex.map(s => `-category:${s}`).join(' ');
}

export const GMAIL_CATEGORY_LABELS: Record<GmailExcludableCategory, string> = {
    promotions: 'Promotions',
    social: 'Social',
    updates: 'Updates',
    forums: 'Forums',
    reservations: 'Reservations',
    purchases: 'Purchases',
};
