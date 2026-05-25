import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { SandboxItemJson } from '../../domain/sandbox/types';
import { SandboxFixtureInspectorSection } from './SandboxFixtureInspectorSection';

const fixtureItem: SandboxItemJson = {
    id: 'fx-instance-1',
    type: 'fixture',
    definition_id: 'fx-def-1',
    definition_kind: 'fixture',
    role: 'solid',
    position: { x: 2, y: 3 },
    color: '#8B5CF6',
};

const definitionContext = {
    fixtureDefinitions: [
        {
            id: 'fx-def-1',
            name: 'steamer',
            label: 'Steamer',
            workflow_id: 'wf-abc-12345678',
            color: '#8B5CF6',
            is_system: false,
        },
    ],
    workflows: [{ id: 'wf-abc-12345678', name: 'Open Door', updated_at: '2026-01-01' }],
};

describe('SandboxFixtureInspectorSection', () => {
    it('shows fixture definition label and workflow name', () => {
        render(
            <SandboxFixtureInspectorSection item={fixtureItem} definitionContext={definitionContext} />,
        );

        expect(screen.getByText('Fixture · Steamer')).toBeTruthy();
        expect(screen.getByText('Steamer')).toBeTruthy();
        expect(screen.getByText('steamer')).toBeTruthy();
        expect(screen.getByText('Open Door')).toBeTruthy();
        expect(screen.getByText('fx-instance-1')).toBeTruthy();
        expect(screen.getByText('#8B5CF6')).toBeTruthy();
    });
});
