import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { AuthClient } from '../api/authClient';
import { User } from '../api/types';

/** Dedupe Google session exchange when React Strict Mode runs the effect twice (dev-only). */
const GOOGLE_SESSION_CONSUMED_KEY = 'mw_google_session_consumed';

export type CheckAuthOptions = { silent?: boolean };

interface AuthContextType {
    user: User | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    login: (username: string, password: string) => Promise<void>;
    logout: () => void | Promise<void>;
    /** Pass `{ silent: true }` to refresh the user without `isLoading` (avoids unmounting the whole app). */
    checkAuth: (opts?: CheckAuthOptions) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
    const [isLoading, setIsLoading] = useState<boolean>(true);

    const checkAuth = useCallback(async (opts?: CheckAuthOptions) => {
        const silent = opts?.silent === true;
        if (!silent) setIsLoading(true);
        performance.mark('mw:auth-check-start');
        try {
            const userData = await AuthClient.getMe();
            performance.mark('mw:auth-check-done');
            setUser(userData);
            setIsAuthenticated(true);
        } catch (error) {
            performance.mark('mw:auth-check-done');
            console.error('Authentication failed:', error);
            setUser(null);
            setIsAuthenticated(false);
        } finally {
            if (!silent) setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        const run = async () => {
            const rawHash = window.location.hash.startsWith('#')
                ? window.location.hash.slice(1)
                : window.location.hash;
            const hashParams = new URLSearchParams(rawHash);
            const googleSession = hashParams.get('google_session');
            if (googleSession) {
                const alreadyDone =
                    sessionStorage.getItem(GOOGLE_SESSION_CONSUMED_KEY) === googleSession;
                if (alreadyDone) {
                    window.history.replaceState(
                        {},
                        '',
                        window.location.pathname + (window.location.search || ''),
                    );
                } else {
                    try {
                        await AuthClient.completeGoogleSession(googleSession);
                        sessionStorage.setItem(GOOGLE_SESSION_CONSUMED_KEY, googleSession);
                        window.history.replaceState(
                            {},
                            '',
                            window.location.pathname + (window.location.search || ''),
                        );
                    } catch (e) {
                        console.error('Google session exchange failed', e);
                        const u = new URL(window.location.href);
                        u.hash = '';
                        u.searchParams.set('google_error', 'session_exchange_failed');
                        window.history.replaceState(
                            {},
                            '',
                            `${u.pathname}?${u.searchParams.toString()}`.replace(/\?$/, ''),
                        );
                    }
                }
            }
            await checkAuth();
        };
        void run();
    }, []);

    const login = async (username: string, password: string) => {
        await AuthClient.login(username, password);
        await checkAuth();
    };

    const logout = async () => {
        try {
            await AuthClient.logout();
        } catch {
            /* still clear local state */
        }
        sessionStorage.removeItem(GOOGLE_SESSION_CONSUMED_KEY);
        setUser(null);
        setIsAuthenticated(false);
    };

    return (
        <AuthContext.Provider value={{ user, isAuthenticated, isLoading, login, logout, checkAuth }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
