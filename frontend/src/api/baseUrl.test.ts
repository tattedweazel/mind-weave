import { describe, expect, it } from 'vitest';

import { resolveDevApiOriginFromLocation } from './baseUrl';

describe('resolveDevApiOriginFromLocation', () => {
    it('maps app host to https api host when page is https', () => {
        expect(
            resolveDevApiOriginFromLocation({ protocol: 'https:', hostname: 'app.example.com' }),
        ).toBe('https://api.example.com');
    });

    it('maps app host to http api:8000 when page is http', () => {
        expect(
            resolveDevApiOriginFromLocation({ protocol: 'http:', hostname: 'app.example.com' }),
        ).toBe('http://api.example.com:8000');
    });

    it('uses same hostname:8000 for localhost', () => {
        expect(resolveDevApiOriginFromLocation({ protocol: 'http:', hostname: 'localhost' })).toBe(
            'http://localhost:8000',
        );
    });

    it('uses same IP:8000 for LAN', () => {
        expect(
            resolveDevApiOriginFromLocation({ protocol: 'http:', hostname: '10.0.0.169' }),
        ).toBe('http://10.0.0.169:8000');
    });
});
