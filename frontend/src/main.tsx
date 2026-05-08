performance.mark('mw:main-start');

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { AuthProvider } from './contexts/AuthContext'
import { ClipboardFeedbackProvider } from './contexts/ClipboardFeedbackContext'
import { ThemeProvider } from './contexts/ThemeContext'
import './index.css'
import 'katex/dist/katex.min.css'

performance.mark('mw:imports-done');

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <AuthProvider>
            <ThemeProvider>
                <ClipboardFeedbackProvider>
                    <App />
                </ClipboardFeedbackProvider>
            </ThemeProvider>
        </AuthProvider>
    </React.StrictMode>,
)

performance.mark('mw:render-called');

if (import.meta.env.DEV) {
    setTimeout(() => {
        const entries = performance.getEntriesByType('mark')
            .filter(e => e.name.startsWith('mw:'))
            .sort((a, b) => a.startTime - b.startTime);
        const t0 = entries[0]?.startTime ?? 0;
        console.groupCollapsed(
            `%c[perf] page load marks (${entries.length})`,
            'color:#6366f1;font-weight:bold',
        );
        for (const e of entries) {
            console.log(`+${(e.startTime - t0).toFixed(0)}ms  ${e.name}`);
        }
        console.groupEnd();
    }, 3000);
}
