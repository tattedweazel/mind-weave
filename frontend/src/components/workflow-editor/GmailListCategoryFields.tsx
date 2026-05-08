import React from 'react';
import {
    GMAIL_CATEGORY_LABELS,
    GMAIL_EXCLUDABLE_CATEGORY_SLUGS,
    normalizeGmailExcludeCategories,
    normalizeGmailInboxFocus,
    type GmailExcludableCategory,
    type GmailInboxFocus,
} from '../../domain/gmailCategoryFilters';

export type GmailFocusMode = 'inherit' | GmailInboxFocus;
export type GmailExcludeMode = 'inherit' | 'custom';

export interface GmailListCategoryFieldsProps {
    nodeData: Record<string, unknown>;
    accountInboxFocus: GmailInboxFocus;
    onPatch: (patch: Record<string, unknown>, deleteKeys?: string[]) => void;
}

export const GmailListCategoryFields: React.FC<GmailListCategoryFieldsProps> = ({
    nodeData,
    accountInboxFocus,
    onPatch,
}) => {
    const skipAccount = nodeData.gmail_skip_account_category_filters === true;

    const focusMode: GmailFocusMode =
        'gmail_inbox_focus' in nodeData
            ? normalizeGmailInboxFocus(nodeData.gmail_inbox_focus)
            : 'inherit';

    const excludeCategories: GmailExcludableCategory[] = 'gmail_exclude_categories' in nodeData
        ? normalizeGmailExcludeCategories(nodeData.gmail_exclude_categories)
        : [];

    const excludeMode: GmailExcludeMode =
        'gmail_exclude_categories' in nodeData ? 'custom' : 'inherit';

    const effectiveFocus =
        focusMode === 'inherit' && !skipAccount
            ? accountInboxFocus
            : focusMode === 'inherit'
              ? 'off'
              : focusMode;

    const showCustomExcludes = excludeMode === 'custom' && !skipAccount;

    return (
        <div className="space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
                <input
                    type="checkbox"
                    checked={skipAccount}
                    onChange={e => onPatch({ gmail_skip_account_category_filters: e.target.checked })}
                    className="rounded border-mw-border"
                />
                <span className="text-xs text-mw-text-primary">Skip account category filters</span>
            </label>
            <div>
                <label className="text-xs font-medium text-mw-text-secondary block mb-1">Inbox focus</label>
                <select
                    value={focusMode}
                    onChange={e => {
                        const v = e.target.value as GmailFocusMode;
                        if (v === 'inherit') {
                            onPatch({}, ['gmail_inbox_focus']);
                        } else {
                            onPatch({ gmail_inbox_focus: v });
                        }
                    }}
                    disabled={skipAccount}
                    className="w-full px-2 py-1.5 text-xs border border-mw-border bg-mw-card text-mw-text-primary rounded-lg disabled:opacity-50"
                >
                    <option value="inherit">
                        Account default
                        {!skipAccount ? ` (${accountInboxFocus === 'primary' ? 'Primary only' : 'All categories'})` : ''}
                    </option>
                    <option value="off">This node: all categories</option>
                    <option value="primary">This node: Primary only</option>
                </select>
            </div>
            <div>
                <label className="text-xs font-medium text-mw-text-secondary block mb-1">Exclude categories</label>
                <div className="flex gap-2">
                    <button
                        type="button"
                        disabled={skipAccount}
                        onClick={() => onPatch({}, ['gmail_exclude_categories'])}
                        className={`text-[11px] px-2 py-1 rounded border ${
                            excludeMode === 'inherit'
                                ? 'border-mw-primary bg-mw-primary-muted text-mw-primary'
                                : 'border-mw-border text-mw-text-secondary hover:bg-mw-card-alt'
                        } disabled:opacity-50`}
                    >
                        Account default
                    </button>
                    <button
                        type="button"
                        disabled={skipAccount}
                        onClick={() => onPatch({ gmail_exclude_categories: [] })}
                        className={`text-[11px] px-2 py-1 rounded border ${
                            excludeMode === 'custom'
                                ? 'border-mw-primary bg-mw-primary-muted text-mw-primary'
                                : 'border-mw-border text-mw-text-secondary hover:bg-mw-card-alt'
                        } disabled:opacity-50`}
                    >
                        Custom
                    </button>
                </div>
                {showCustomExcludes ? (
                    <>
                        <div className="space-y-1.5 pl-0.5 mt-2">
                            {GMAIL_EXCLUDABLE_CATEGORY_SLUGS.map(slug => (
                                <label key={slug} className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={excludeCategories.includes(slug)}
                                        disabled={effectiveFocus === 'primary'}
                                        onChange={e => {
                                            const next = new Set(excludeCategories);
                                            if (e.target.checked) next.add(slug);
                                            else next.delete(slug);
                                            onPatch({
                                                gmail_exclude_categories: GMAIL_EXCLUDABLE_CATEGORY_SLUGS.filter(s =>
                                                    next.has(s),
                                                ),
                                            });
                                        }}
                                        className="rounded border-mw-border"
                                    />
                                    <span className="text-xs text-mw-text-primary">{GMAIL_CATEGORY_LABELS[slug]}</span>
                                </label>
                            ))}
                        </div>
                        {effectiveFocus === 'primary' ? (
                            <p className="text-[10px] text-mw-text-secondary mt-2">
                                Primary-only focus is applied; category exclusions are ignored in the final query (same as
                                Gmail API behavior).
                            </p>
                        ) : null}
                    </>
                ) : null}
            </div>
        </div>
    );
};
