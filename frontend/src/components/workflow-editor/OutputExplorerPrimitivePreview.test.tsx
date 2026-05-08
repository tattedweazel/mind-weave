import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PrimitiveValuePreview, safeJsonStringify } from './OutputExplorerPrimitivePreview';

describe('safeJsonStringify', () => {
    it('pretty-prints objects', () => {
        expect(safeJsonStringify({ a: 1 }, 2)).toBe('{\n  "a": 1\n}');
    });

    it('falls back when JSON.stringify throws', () => {
        const circular: Record<string, unknown> = {};
        circular.self = circular;
        const out = safeJsonStringify(circular, 2);
        expect(out).toBeTruthy();
        expect(typeof out).toBe('string');
    });
});

describe('PrimitiveValuePreview', () => {
    it('shows pretty-print hint and JSON for object payloads', () => {
        render(<PrimitiveValuePreview payload={{ x: 2 }} typeHint="dictionary" />);
        expect(screen.getByText(/pretty-printed JSON/i)).toBeInTheDocument();
        expect(screen.getByText(/"x": 2/)).toBeInTheDocument();
    });

    it('shows collapsible-tree hint for arrays', () => {
        render(<PrimitiveValuePreview payload={[1, 2]} />);
        expect(screen.getByText(/collapsible tree navigator/i)).toBeInTheDocument();
    });

    it('renders empty string as em dash', () => {
        render(<PrimitiveValuePreview payload="   " />);
        expect(screen.getByText('—')).toBeInTheDocument();
    });

    it('renders inferred type hint when provided', () => {
        render(<PrimitiveValuePreview payload={null} typeHint="dictionary" />);
        expect(screen.getByText('dictionary')).toBeInTheDocument();
    });

    it('renders bigint via fallback branch', () => {
        render(<PrimitiveValuePreview payload={BigInt(7)} />);
        expect(screen.getByText('7')).toBeInTheDocument();
    });
});
