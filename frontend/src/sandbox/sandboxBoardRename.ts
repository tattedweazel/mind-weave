export function normalizeBoardName(draft: string, fallback: string): string {
    const trimmed = draft.trim();
    return trimmed || fallback;
}

export function shouldCommitBoardRename(args: {
    currentName: string;
    draftName: string;
    isSystem: boolean;
}): boolean {
    if (args.isSystem) return false;
    const normalized = args.draftName.trim();
    if (!normalized) return false;
    return normalized !== args.currentName;
}
