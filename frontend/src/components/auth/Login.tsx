import React, { useState, useEffect } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { AuthClient } from '../../api/authClient';
import { Bot, KeyRound, User as UserIcon, Loader2, ChevronDown, ChevronUp } from 'lucide-react';

const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
    denied: 'Google authorization was denied.',
    expired: 'Google authorization expired. Please try again.',
    missing_params: 'Google authorization failed: missing parameters.',
    exchange_failed: 'Google authorization failed. Please try again.',
    session_exchange_failed:
        'Could not complete sign-in with the server (session expired or API URL misconfigured). Check VITE_API_BASE matches your backend origin (e.g. http://localhost:8000 without /api/v1) and try again.',
    already_linked: 'This Google account is already linked to another user.',
    no_account: 'No Mind Weave account is linked to this Google account. Please ask an admin to create your account and associate it with Google.',
    not_configured: 'Google sign-in is not configured.',
};

export const Login: React.FC = () => {
    const { login } = useAuth();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [showPasswordForm, setShowPasswordForm] = useState(false);

    // Handle google_error from URL
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const googleError = params.get('google_error');
        if (googleError) {
            setError(GOOGLE_ERROR_MESSAGES[googleError] || `Google sign-in failed: ${googleError}`);
            window.history.replaceState({}, '', window.location.pathname);
        }
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setIsSubmitting(true);
        try {
            await login(username, password);
        } catch (err: any) {
            if (err.message === 'USE_GOOGLE_LOGIN') {
                setError('This account uses Google sign-in. Please sign in with your Google account.');
                setShowPasswordForm(false);
                // Redirect to Google login after a brief moment so user sees the message
                setTimeout(() => {
                    window.location.href = AuthClient.getGoogleLoginUrl();
                }, 1500);
            } else {
                setError(err.message || 'Login failed. Please check your credentials.');
            }
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleShowPasswordForm = () => {
        setShowPasswordForm(true);
        setError(null);
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-mw-page px-4">
            <div className="max-w-md w-full space-y-8 bg-mw-card p-8 rounded-2xl shadow-xl border border-mw-border">
                <div className="text-center">
                    <div className="mx-auto h-16 w-16 bg-mw-primary-muted rounded-full flex items-center justify-center mb-4">
                        <Bot size={32} className="text-mw-primary" />
                    </div>
                    <h2 className="text-3xl font-extrabold text-mw-text-primary tracking-tight">
                        Welcome Back
                    </h2>
                    <p className="mt-2 text-sm text-mw-text-secondary">
                        Sign in to access your Mind Weave
                    </p>
                </div>

                <div className="mt-8 space-y-6">
                    {error && (
                        <div className="bg-mw-error-muted border border-mw-error text-mw-error px-4 py-3 rounded-lg text-sm">
                            {error}
                        </div>
                    )}

                    {/* Primary: Sign in with Google */}
                    <a
                        href={AuthClient.getGoogleLoginUrl()}
                        className="w-full flex justify-center items-center gap-2 py-2.5 px-4 border border-mw-border rounded-lg text-sm font-medium text-mw-text-primary bg-mw-sidebar hover:bg-mw-card-alt focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-mw-card focus:ring-mw-primary transition-colors"
                    >
                        <svg className="w-5 h-5" viewBox="0 0 24 24">
                            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                        </svg>
                        Sign in with Google
                    </a>

                    {/* Secondary: Login with Username/Password */}
                    <div className="relative">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-mw-border" />
                        </div>
                        <div className="relative flex justify-center text-sm">
                            <span className="px-2 bg-mw-card text-mw-text-secondary">or</span>
                        </div>
                    </div>

                    {!showPasswordForm ? (
                        <button
                            type="button"
                            onClick={handleShowPasswordForm}
                            className="w-full flex justify-center items-center gap-2 py-2 text-sm text-mw-text-secondary hover:text-mw-text-primary transition-colors"
                        >
                            <ChevronDown size={16} />
                            Login with Username/Password
                        </button>
                    ) : (
                        <form className="space-y-4" onSubmit={handleSubmit}>
                            <div className="space-y-4 rounded-md shadow-sm">
                                <div className="relative">
                                    <label className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide">Username</label>
                                    <div className="relative mt-1">
                                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                            <UserIcon size={16} className="text-mw-text-secondary" />
                                        </div>
                                        <input
                                            type="text"
                                            required
                                            autoFocus
                                            className="appearance-none rounded-lg relative block w-full px-3 py-2 pl-10 border border-mw-border placeholder-mw-text-secondary text-mw-text-primary bg-mw-sidebar focus:outline-none focus:ring-2 focus:ring-mw-primary focus:border-mw-primary focus:z-10 sm:text-sm"
                                            placeholder="Username"
                                            value={username}
                                            onChange={(e) => setUsername(e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="relative">
                                    <label className="text-xs font-semibold text-mw-text-secondary uppercase tracking-wide">Password</label>
                                    <div className="relative mt-1">
                                        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                            <KeyRound size={16} className="text-mw-text-secondary" />
                                        </div>
                                        <input
                                            type="password"
                                            required
                                            className="appearance-none rounded-lg relative block w-full px-3 py-2 pl-10 border border-mw-border placeholder-mw-text-secondary text-mw-text-primary bg-mw-sidebar focus:outline-none focus:ring-2 focus:ring-mw-primary focus:border-mw-primary focus:z-10 sm:text-sm"
                                            placeholder="Password"
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                        />
                                    </div>
                                </div>
                            </div>

                            <div className="flex gap-2">
                                <button
                                    type="submit"
                                    disabled={isSubmitting || !username || !password}
                                    className="flex-1 flex justify-center items-center py-2.5 px-4 border border-transparent text-sm font-medium rounded-lg text-white bg-mw-primary hover:bg-mw-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-mw-card focus:ring-mw-primary disabled:opacity-70 disabled:cursor-not-allowed transition-colors"
                                >
                                    {isSubmitting ? <Loader2 size={18} className="animate-spin" /> : 'Sign in'}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setShowPasswordForm(false)}
                                    className="flex justify-center items-center py-2.5 px-3 text-sm text-mw-text-secondary hover:text-mw-text-primary transition-colors"
                                    title="Hide form"
                                >
                                    <ChevronUp size={18} />
                                </button>
                            </div>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
};
