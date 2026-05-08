import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TtsBridgeOptionsTextarea } from './TtsBridgeOptionsTextarea';

describe('TtsBridgeOptionsTextarea', () => {
    it('keeps invalid partial JSON in the field while typing', () => {
        const onCommit = vi.fn();
        render(
            <TtsBridgeOptionsTextarea ttsOptions={{}} onFocus={() => {}} onCommit={onCommit} />,
        );
        const ta = screen.getByRole('textbox');
        expect(ta).toHaveValue('{}');
        fireEvent.change(ta, { target: { value: '' } });
        expect(onCommit).toHaveBeenCalledWith({});
        fireEvent.change(ta, { target: { value: '{"instruct":' } });
        expect(ta).toHaveValue('{"instruct":');
        expect(onCommit).toHaveBeenCalledTimes(1);
    });

    it('commits when JSON becomes a valid object', () => {
        const onCommit = vi.fn();
        render(
            <TtsBridgeOptionsTextarea ttsOptions={{}} onFocus={() => {}} onCommit={onCommit} />,
        );
        const ta = screen.getByRole('textbox');
        fireEvent.change(ta, { target: { value: '{"a":1}' } });
        expect(onCommit).toHaveBeenCalledWith({ a: 1 });
    });

    it('resets draft when ttsOptions prop changes externally', () => {
        const { rerender } = render(
            <TtsBridgeOptionsTextarea ttsOptions={{}} onFocus={() => {}} onCommit={vi.fn()} />,
        );
        const ta = screen.getByRole('textbox');
        expect(ta).toHaveValue('{}');
        rerender(
            <TtsBridgeOptionsTextarea
                ttsOptions={{ instruct: 'x' }}
                onFocus={() => {}}
                onCommit={vi.fn()}
            />,
        );
        expect(ta).toHaveValue('{\n  "instruct": "x"\n}');
    });
});
