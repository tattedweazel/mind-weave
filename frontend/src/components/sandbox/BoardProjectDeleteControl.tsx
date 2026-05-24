import React, { useState } from 'react';
import { Trash2 } from 'lucide-react';

import { boardProjectDeleteConfirmMessage } from '../../domain/boardProjectMembership';

type BoardProjectDeleteControlProps = {
    projectName: string;
    boardCount: number;
    disabled?: boolean;
    onConfirmDelete: () => Promise<void>;
};

export function BoardProjectDeleteControl({
    projectName,
    boardCount,
    disabled = false,
    onConfirmDelete,
}: BoardProjectDeleteControlProps) {
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState(false);

    if (disabled) {
        return null;
    }

    const handleDelete = async (e: React.MouseEvent) => {
        e.stopPropagation();
        setBusy(true);
        try {
            await onConfirmDelete();
            setConfirming(false);
        } catch {
            /* parent may surface errors */
        } finally {
            setBusy(false);
        }
    };

    if (confirming) {
        return (
            <div
                className="flex items-center gap-1 shrink-0 max-w-[12rem]"
                onClick={e => e.stopPropagation()}
            >
                <span
                    className="text-[10px] font-medium text-red-500 leading-tight truncate"
                    title={boardProjectDeleteConfirmMessage(projectName, boardCount)}
                >
                    {boardProjectDeleteConfirmMessage(projectName, boardCount)}
                </span>
                <button
                    type="button"
                    disabled={busy}
                    onClick={handleDelete}
                    className="px-1.5 py-0.5 text-[10px] bg-red-500 text-white rounded hover:bg-red-600 font-medium disabled:opacity-50"
                >
                    Delete
                </button>
                <button
                    type="button"
                    disabled={busy}
                    onClick={e => {
                        e.stopPropagation();
                        setConfirming(false);
                    }}
                    className="px-1.5 py-0.5 text-[10px] bg-mw-card-alt text-mw-text-primary rounded hover:opacity-90 font-medium disabled:opacity-50"
                >
                    Cancel
                </button>
            </div>
        );
    }

    return (
        <button
            type="button"
            onClick={e => {
                e.stopPropagation();
                setConfirming(true);
            }}
            className="p-1 text-mw-text-secondary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors shrink-0"
            title="Delete project"
        >
            <Trash2 size={14} />
        </button>
    );
}
