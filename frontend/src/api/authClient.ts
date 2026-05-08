import { User, Token } from './types';
import { API_BASE } from './baseUrl';
import { apiErrorFromResponse, fetchWithCredentials, parseFastApiDetail, readJsonBody } from './http';

export class AuthClient {
    static async login(username: string, password: string): Promise<Token> {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetchWithCredentials(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData,
        });

        if (!response.ok) {
            if (response.status === 401) {
                throw new Error('Invalid credentials');
            }
            const data = await readJsonBody(response);
            if (response.status === 400 && parseFastApiDetail(data) === 'use_google_login') {
                throw new Error('USE_GOOGLE_LOGIN');
            }
            throw apiErrorFromResponse(response, data);
        }

        return response.json();
    }

    static async completeGoogleSession(code: string): Promise<Token> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/google/session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code }),
        });
        if (!response.ok) {
            const data = await readJsonBody(response);
            const detail = parseFastApiDetail(data);
            throw new Error(
                detail ? `Google session exchange failed: ${detail}` : `Google session exchange failed: ${response.statusText}`,
            );
        }
        return response.json();
    }

    static async refreshSession(): Promise<Token> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/refresh`, { method: 'POST' });
        if (!response.ok) {
            const data = await readJsonBody(response);
            const detail = parseFastApiDetail(data);
            throw new Error(detail ? `Refresh failed: ${detail}` : `Refresh failed: ${response.statusText}`);
        }
        return response.json();
    }

    static async logout(): Promise<void> {
        await fetchWithCredentials(`${API_BASE}/auth/logout`, { method: 'POST' });
    }

    static getGoogleLoginUrl(): string {
        return `${API_BASE}/auth/google/login`;
    }

    static async register(username: string, password: string): Promise<void> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password }),
        });

        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }
    }

    static async getMe(): Promise<User> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/me`, {});
        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }

        return response.json();
    }

    static async updateMe(data: {
        settings?: Record<string, any>;
        api_keys?: Record<string, string>;
    }): Promise<User> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/me`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }

        return response.json();
    }

    static async getUsers(): Promise<User[]> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/users`, {});
        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }

        return response.json();
    }

    static async deleteUser(userId: string): Promise<void> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/users/${userId}`, {
            method: 'DELETE',
        });
        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }
    }

    static async adminCreateUser(
        username: string,
        password: string,
        is_admin: boolean,
    ): Promise<void> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, is_admin }),
        });

        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }
    }

    static async adminUpdateUser(
        userId: string,
        data: { username?: string; password?: string; is_admin?: boolean },
    ): Promise<void> {
        const body: Record<string, unknown> = {};
        if (data.username !== undefined) body.username = data.username;
        if (data.password !== undefined) body.password = data.password;
        if (data.is_admin !== undefined) body.is_admin = data.is_admin;

        const response = await fetchWithCredentials(`${API_BASE}/auth/users/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }
    }

    static async getGoogleAuthorizeUrl(): Promise<{ redirect_url: string }> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/google/authorize`, {
            method: 'POST',
        });
        if (!response.ok) {
            if (response.status === 503) {
                throw new Error('Google OAuth is not configured');
            }
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }
        return response.json();
    }

    static async disassociateGoogle(): Promise<void> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/google/disassociate`, {
            method: 'POST',
        });
        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }
    }

    static async adminDisassociateGoogle(userId: string): Promise<void> {
        const response = await fetchWithCredentials(`${API_BASE}/auth/users/${userId}/google/disassociate`, {
            method: 'POST',
        });
        if (!response.ok) {
            throw apiErrorFromResponse(response, await readJsonBody(response));
        }
    }
}
