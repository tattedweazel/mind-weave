import React, { useState } from 'react';
import { Trash2 } from 'lucide-react';

import { boardDeleteConfirmMessage } from '../../domain/boardProjectMembership';

export type BoardDeleteControlVariant = 'sidebar' | 'toolbar';

type BoardDeleteControlProps = {
    boardName: string;
    disabled?: boolean;
    variant?: BoardDeleteControlVariant;
    onConfirmDelete: () => Promise<void>;
};

export function BoardDeleteControl({
    boardName,
    disabled = false,
    variant = 'sidebar',
    onConfirmDelete,
}: BoardDeleteControlProps) {
    const [confirming, setConfirming] = useState(false);
    const [busy, setBusy] = useState(false);

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
        const confirmLabel = variant === 'toolbar' ? 'Yes' : 'Delete';
        const cancelLabel = 'Cancel';
        return (
            <div
                className={
                    variant === 'toolbar'
                        ? 'flex items-center gap-1.5 shrink-0'
                        : 'flex items-center gap-1 shrink-0 max-w-[10rem]'
                }
                onClick={e => e.stopPropagation()}
            >
                <span
                    className={
                        variant === 'toolbar'
                            ? 'text-xs font-medium text-red-500'
                            : 'text-[10px] font-medium text-red-500 leading-tight truncate'
                    }
                    title={boardDeleteConfirmMessage(boardName)}
                >
                    {boardDeleteConfirmMessage(boardName)}
                </span>
                <button
                    type="button"
                    disabled={busy || disabled}
                    onClick={handleDelete}
                    className={
                        variant === 'toolbar'
                            ? 'px-2 py-1 text-xs font-medium text-white bg-red-500 hover:bg-red-600 rounded shadow-sm transition-colors disabled:opacity-50'
                            : 'px-1.5 py-0.5 text-[10px] bg-red-500 text-white rounded hover:bg-red-600 font-medium disabled:opacity-50'
                    }
                >
                    {confirmLabel}
                </button>
                <button
                    type="button"
                    disabled={busy}
                    onClick={e => {
                        e.stopPropagation();
                        setConfirming(false);
                    }}
                    className={
                        variant === 'toolbar'
                            ? 'px-2 py-1 text-xs font-medium text-mw-text-primary bg-mw-card-alt rounded hover:opacity-90 disabled:opacity-50'
                            : 'px-1.5 py-0.5 text-[10px] bg-mw-card-alt text-mw-text-primary rounded hover:opacity-90 font-medium disabled:opacity-50'
                    }
                >
                    {cancelLabel}
                </button>
            </div>
        );
    }

    return (
        <button
            type="button"
            disabled={disabled}
            onClick={e => {
                e.stopPropagation();
                setConfirming(true);
            }}
            className={
                variant === 'toolbar'
                    ? 'p-1.5 text-mw-text-secondary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors shrink-0 disabled:opacity-50'
                    : 'p-1 text-mw-text-secondary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors shrink-0 disabled:opacity-50'
            }
            title="Delete board"
            aria-label="Delete board"
        >
            <Trash2 size={variant === 'toolbar' ? 16 : 14} />
        </button>
    );
}
