import { describe, expect, it } from 'vitest';

import type { WorkflowDefinition } from '../api/types';
import {
    autoReasonForUserAction,
    buildCreatureUserActionsPayload,
    creaturesRequiringUserAction,
    graphRequiresSimulationUserAction,
    promptUserActionNodeIdFromGraph,
} from './sandboxPromptUserAction';

const graphWithPrompt: WorkflowDefinition['graph'] = {
    nodes: [
        { id: 'start', kind: 'start', label: 'Start', data: {}, position: { x: 0, y: 0 } },
        {
            id: 'prompt-1',
            kind: 'utility',
            utility_type: 'sandbox_prompt_user_action',
            label: 'Prompt',
            data: {},
            position: { x: 100, y: 0 },
        },
        { id: 'stop', kind: 'stop', label: 'Stop', data: {}, position: { x: 200, y: 0 } },
    ],
    edges: [],
};

describe('sandboxPromptUserAction', () => {
    it('detects prompt node id', () => {
        expect(promptUserActionNodeIdFromGraph(graphWithPrompt)).toBe('prompt-1');
        expect(graphRequiresSimulationUserAction(graphWithPrompt)).toBe(true);
        expect(promptUserActionNodeIdFromGraph({ nodes: [], edges: [] })).toBeNull();
    });

    it('builds auto reason and tick payload', () => {
        expect(autoReasonForUserAction({ action: 'move_forward' })).toBe('user: move_forward');
        expect(
            autoReasonForUserAction({ action: 'place_item', item_type: 'ball' }),
        ).toBe('user: place_item:ball');
        expect(
            autoReasonForUserAction({
                action: 'place_item',
                item_type: 'ball',
                inventory_index: 2,
            }),
        ).toBe('user: place_item:ball@2');
        expect(
            buildCreatureUserActionsPayload({
                c1: { action: 'turn_left' },
                c2: { action: 'place_item', item_type: 'food', inventory_index: 1 },
                c3: { action: 'use_fixture' },
            }),
        ).toEqual({
            c1: { action: 'turn_left' },
            c2: { action: 'place_item', item_type: 'food', inventory_index: 1 },
            c3: { action: 'use_fixture' },
        });
        expect(autoReasonForUserAction({ action: 'use_fixture' })).toBe('user: use_fixture');
    });

    it('filters creatures requiring user action', () => {
        const creatures = [
            { id: 'a', workflow_id: 'wf-prompt', position: { x: 0, y: 0 }, facing: 'N' as const },
            { id: 'b', workflow_id: 'wf-other', position: { x: 1, y: 0 }, facing: 'N' as const },
        ];
        const map = new Map<string, WorkflowDefinition | null>([
            ['wf-prompt', { id: 'wf-prompt', name: 'P', graph: graphWithPrompt } as WorkflowDefinition],
            ['wf-other', { id: 'wf-other', name: 'O', graph: { nodes: [], edges: [] } } as WorkflowDefinition],
        ]);
        expect(creaturesRequiringUserAction(creatures, map).map(c => c.id)).toEqual(['a']);
    });
});
