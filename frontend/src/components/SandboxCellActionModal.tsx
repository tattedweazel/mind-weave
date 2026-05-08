/**
 * Stepped cell actions: choose root action → optional item type. Extend registry as features grow.
 */
import React from 'react';
import { ChevronLeft, X } from 'lucide-react';

import type { SandboxGridCellJson } from '../domain/sandbox/types';
import { placeFoodInteraction, removeItemAtCellInteraction, type SandboxCellInteraction } from '../sandbox/sandboxCellInteractions';

export type CellActionWizardStep = 'choose_action' | 'choose_item_type';

const ROOT_ACTIONS = [
    { id: 'place_item' as const, label: 'Place item', description: 'Put something on this cell' },
    { id: 'remove_item' as const, label: 'Remove item', description: 'Clear items from this cell' },
];

const PLACE_ITEM_TYPES = [{ id: 'food' as const, label: 'Food', description: 'Energy for the creature' }];

export interface SandboxCellActionModalProps {
    cell: SandboxGridCellJson;
    /** When true, show Inspect (opens Explorer); no tick interaction. */
    canInspect?: boolean;
    initialStep?: CellActionWizardStep;
    onComplete: (interaction: SandboxCellInteraction) => void;
    onDismiss: () => void;
    onInspect?: () => void;
}

export const SandboxCellActionModal: React.FC<SandboxCellActionModalProps> = ({
    cell,
    canInspect = false,
    initialStep = 'choose_action',
    onComplete,
    onDismiss,
    onInspect,
}) => {
    const [step, setStep] = React.useState<CellActionWizardStep>(initialStep);
    const [chosenAction, setChosenAction] = React.useState<(typeof ROOT_ACTIONS)[number]['id'] | null>(null);

    React.useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onDismiss();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [onDismiss]);

    const title = `Cell (${cell.x}, ${cell.y})`;

    const goBack = () => {
        if (step === 'choose_item_type') {
            setStep('choose_action');
            setChosenAction(null);
            return;
        }
        onDismiss();
    };

    return (
        <div
            className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm p-4"
            onClick={onDismiss}
            role="presentation"
        >
            <div
                className="w-full max-w-md rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-xl overflow-hidden"
                onClick={e => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-labelledby="sandbox-cell-action-title"
            >
                <div className="flex items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-700 px-4 py-3">
                    <div className="flex items-center gap-2 min-w-0">
                        {step !== 'choose_action' ? (
                            <button
                                type="button"
                                onClick={goBack}
                                className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                                aria-label="Back"
                            >
                                <ChevronLeft className="h-5 w-5" />
                            </button>
                        ) : null}
                        <h2 id="sandbox-cell-action-title" className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                            {title}
                        </h2>
                    </div>
                    <button
                        type="button"
                        onClick={onDismiss}
                        className="shrink-0 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                        aria-label="Close"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="p-4 space-y-3">
                    {step === 'choose_action' ? (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Actions</p>
                            <ul className="space-y-2">
                                {canInspect && onInspect ? (
                                    <li key="inspect">
                                        <button
                                            type="button"
                                            aria-label="Inspect"
                                            className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2.5 hover:border-sky-500 dark:hover:border-sky-500 hover:bg-sky-50/50 dark:hover:bg-sky-950/30 transition-colors"
                                            onClick={() => onInspect()}
                                        >
                                            <span className="block text-sm font-medium text-slate-900 dark:text-slate-100">
                                                Inspect
                                            </span>
                                            <span className="block text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                                                View what is on this cell in the Explorer panel
                                            </span>
                                        </button>
                                    </li>
                                ) : null}
                                {ROOT_ACTIONS.map(a => (
                                    <li key={a.id}>
                                        <button
                                            type="button"
                                            aria-label={a.label}
                                            className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2.5 hover:border-sky-500 dark:hover:border-sky-500 hover:bg-sky-50/50 dark:hover:bg-sky-950/30 transition-colors"
                                            onClick={() => {
                                                if (a.id === 'remove_item') {
                                                    onComplete(removeItemAtCellInteraction(cell));
                                                    return;
                                                }
                                                setChosenAction(a.id);
                                                setStep('choose_item_type');
                                            }}
                                        >
                                            <span className="block text-sm font-medium text-slate-900 dark:text-slate-100">{a.label}</span>
                                            <span className="block text-xs text-slate-500 dark:text-slate-400 mt-0.5">{a.description}</span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </>
                    ) : (
                        <>
                            <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Item type</p>
                            <ul className="space-y-2">
                                {PLACE_ITEM_TYPES.map(t => (
                                    <li key={t.id}>
                                        <button
                                            type="button"
                                            aria-label={t.label}
                                            className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-600 px-3 py-2.5 hover:border-sky-500 dark:hover:border-sky-500 hover:bg-sky-50/50 dark:hover:bg-sky-950/30 transition-colors"
                                            onClick={() => {
                                                if (chosenAction === 'place_item' && t.id === 'food') {
                                                    onComplete(placeFoodInteraction(cell));
                                                }
                                            }}
                                        >
                                            <span className="block text-sm font-medium text-slate-900 dark:text-slate-100">{t.label}</span>
                                            <span className="block text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t.description}</span>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};
