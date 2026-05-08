/**
 * App-wide copy-to-clipboard with a short confirmation toast.
 * Use `useCopyWithFeedback()` from any Copy control; do not call `navigator.clipboard.writeText` directly for user-initiated copy actions.
 * `useStatusToast()` shows the same toast chrome for arbitrary status messages (e.g. TTS playback errors).
 */

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { writeTextToSystemClipboard } from '../systemClipboard';

const SUCCESS_MESSAGE = 'Copied to clipboard';
const ERROR_MESSAGE = 'Could not copy';

type CopyWithFeedbackFn = (text: string) => Promise<void>;
type ShowStatusToastFn = (message: string, isError?: boolean) => void;

type ClipboardFeedbackContextValue = {
    copyWithFeedback: CopyWithFeedbackFn;
    showStatusToast: ShowStatusToastFn;
};

const ClipboardFeedbackContext = createContext<ClipboardFeedbackContextValue | null>(null);

export function ClipboardFeedbackProvider({ children }: { children: React.ReactNode }) {
    const [toast, setToast] = useState<{ message: string; isError: boolean } | null>(null);

    const showStatusToast = useCallback<ShowStatusToastFn>((message, isError = false) => {
        setToast({ message, isError });
    }, []);

    const copyWithFeedback = useCallback(async (text: string) => {
        try {
            await writeTextToSystemClipboard(text);
            setToast({ message: SUCCESS_MESSAGE, isError: false });
        } catch {
            setToast({ message: ERROR_MESSAGE, isError: true });
        }
    }, []);

    const value = useMemo(
        () => ({
            copyWithFeedback,
            showStatusToast,
        }),
        [copyWithFeedback, showStatusToast],
    );

    useEffect(() => {
        if (!toast) return;
        const t = window.setTimeout(() => setToast(null), 2500);
        return () => clearTimeout(t);
    }, [toast]);

    return (
        <ClipboardFeedbackContext.Provider value={value}>
            {children}
            {toast ?
                <div
                    role="status"
                    aria-live="polite"
                    className={`fixed bottom-4 left-1/2 z-[70] -translate-x-1/2 px-4 py-2.5 rounded-lg shadow-lg border text-sm font-medium max-w-[min(90vw,24rem)] text-center ${
                        toast.isError ?
                            'bg-mw-error-muted text-mw-error border-mw-error'
                        :   'bg-mw-card border-mw-border text-mw-text-primary'
                    }`}
                >
                    {toast.message}
                </div>
            :   null}
        </ClipboardFeedbackContext.Provider>
    );
}

export function useCopyWithFeedback(): CopyWithFeedbackFn {
    const ctx = useContext(ClipboardFeedbackContext);
    if (!ctx) {
        throw new Error('useCopyWithFeedback must be used within ClipboardFeedbackProvider');
    }
    return ctx.copyWithFeedback;
}

export function useStatusToast(): ShowStatusToastFn {
    const ctx = useContext(ClipboardFeedbackContext);
    if (!ctx) {
        throw new Error('useStatusToast must be used within ClipboardFeedbackProvider');
    }
    return ctx.showStatusToast;
}
