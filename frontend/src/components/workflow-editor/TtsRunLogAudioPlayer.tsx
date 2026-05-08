import { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import { createObjectUrlForAudioBase64, downloadAudioBase64 } from '../../domain/ttsAudioPlayback';

export type TtsRunLogAudioPlayerProps = {
    base64: string;
    mimeType: string;
    nodeId: string;
};

/**
 * Inline player + download for a single TTS node result (live run only; base64 must be present).
 * Object URLs are created in an effect (not useMemo) so React StrictMode mount/unmount pairs do not
 * revoke a URL while the first `<audio>` instance still references it.
 */
export function TtsRunLogAudioPlayer({ base64, mimeType, nodeId }: TtsRunLogAudioPlayerProps) {
    const [objectUrl, setObjectUrl] = useState<string | null>(null);

    useEffect(() => {
        let url: string;
        try {
            url = createObjectUrlForAudioBase64(base64, mimeType);
        } catch {
            setObjectUrl(null);
            return;
        }
        setObjectUrl(url);
        return () => {
            // Revoking synchronously in StrictMode/unmount can invalidate the URL before `<audio>` finishes
            // decoding (grey 0:00). Defer so the element can attach and load.
            const u = url;
            window.setTimeout(() => URL.revokeObjectURL(u), 2_000);
        };
    }, [base64, mimeType]);

    const safeName = useMemo(() => {
        const safeId = nodeId.replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 48);
        const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        return `tts-${safeId}-${stamp}.wav`;
    }, [nodeId, base64]);
    return (
        <div className="space-y-2">
            {objectUrl ?
                <audio
                    key={objectUrl}
                    controls
                    className="w-full max-w-md h-9"
                    preload="auto"
                    src={objectUrl}
                />
            :   <p className="text-xs text-mw-text-secondary">Preparing audio…</p>}
            <button
                type="button"
                onClick={() => downloadAudioBase64(base64, mimeType, safeName)}
                className="inline-flex items-center gap-1.5 px-2 py-1 text-[11px] font-medium rounded-md border border-mw-border bg-mw-card-alt text-mw-text-primary hover:bg-mw-card transition-colors"
            >
                <Download size={12} />
                Download WAV
            </button>
        </div>
    );
}
