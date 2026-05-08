/**
 * Canonical workflow palette colors — keep in sync with backend
 * `app/domain/palette_defaults.py` (CQ-001).
 *
 * `DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME` / `DEFAULT_BUILTIN_WORKFLOW_PALETTE_SLUG`
 * match backend `DEFAULT_PALETTE_NAME` / `DEFAULT_PALETTE_SLUG`.
 *
 * For new node types: update backend palette_defaults, then mirror here.
 *
 * Optional palette keys (same strings as manifest `kind`) apply a color to an
 * entire step family when no specific key is set: `primitive`, `skill`,
 * `utility`, `control`. Backend stores them in `Palette.colors` like any other
 * key; only the SPA resolves the hierarchy.
 */

/** Matches backend `DEFAULT_PALETTE_NAME` in `palette_defaults.py`. */
export const DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME = 'Default';

/** Matches backend `DEFAULT_PALETTE_SLUG` in `palette_defaults.py`. */
export const DEFAULT_BUILTIN_WORKFLOW_PALETTE_SLUG = 'default';

/** Minimal shape for palette list fallback (editor, tests). */
export type WorkflowPaletteListEntry = {
    name: string;
    user_id: string | null;
    slug?: string | null;
};

/** Built-in **Default** system preset (slug preferred; name fallback for older rows). */
export function isBuiltinDefaultSystemPalette(p: WorkflowPaletteListEntry): boolean {
    return (
        p.user_id == null &&
        (p.slug === DEFAULT_BUILTIN_WORKFLOW_PALETTE_SLUG ||
            (p.slug == null && p.name === DEFAULT_BUILTIN_WORKFLOW_PALETTE_NAME))
    );
}

/**
 * When `palette_id` is unset: use the system **Default** preset if present,
 * else the first system palette by name (stable). User-owned palettes are ignored.
 */
export function resolveFallbackWorkflowPalette<T extends WorkflowPaletteListEntry>(
    palettes: readonly T[],
): T | null {
    const systemDefault = palettes.find(isBuiltinDefaultSystemPalette);
    if (systemDefault) return systemDefault;
    const system = palettes
        .filter(p => p.user_id == null)
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name));
    return system[0] ?? null;
}

/** System presets first (Default, then A–Z), then user palettes A–Z. */
export function sortWorkflowPalettesForDisplay<T extends WorkflowPaletteListEntry>(palettes: readonly T[]): T[] {
    const system = palettes.filter(p => p.user_id == null);
    const userOwned = palettes.filter(p => p.user_id != null);
    const defaultNamed = system.filter(isBuiltinDefaultSystemPalette);
    const systemRest = system
        .filter(p => !isBuiltinDefaultSystemPalette(p))
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name));
    userOwned.sort((a, b) => a.name.localeCompare(b.name));
    return [...defaultNamed, ...systemRest, ...userOwned];
}

/** Manifest-aligned step families for optional aggregate palette keys. */
export type WorkflowPaletteFamily = 'primitive' | 'skill' | 'utility' | 'control';

export const WORKFLOW_PALETTE_FAMILY_KEYS: readonly WorkflowPaletteFamily[] = [
    'primitive',
    'skill',
    'utility',
    'control',
];

/** Maps each per-step palette handle key (except `any`, `workflow`) to its family. */
export const PALETTE_KEY_TO_FAMILY: Partial<Record<string, WorkflowPaletteFamily>> = {
    string: 'primitive',
    list: 'primitive',
    dictionary: 'primitive',
    structure: 'primitive',
    document: 'primitive',
    image: 'primitive',
    gmail: 'primitive',
    sandbox_behavior: 'primitive',
    decision_action: 'utility',
    sandbox_tick: 'utility',
    boolean: 'primitive',
    int: 'primitive',
    datetime: 'primitive',
    simple_llm_call: 'skill',
    multimodal_llm: 'skill',
    text_to_speech: 'skill',
    transcribe_audio: 'skill',
    audio_file_input: 'skill',
    transcribe_file: 'skill',
    audio: 'skill',
    gmail_list_messages: 'skill',
    calendar_list_events: 'skill',
    fetch_url: 'skill',
    capture_url_snapshot: 'skill',
    list_to_string: 'utility',
    string_to_list: 'utility',
    prepend_text: 'utility',
    string_trunc: 'utility',
    message: 'utility',
    len_from_list: 'utility',
    random_item_from_list: 'utility',
    int_to_string: 'utility',
    list_item_by_index: 'utility',
    dictionary_value_by_key: 'utility',
    dictionary_set_value_by_key: 'utility',
    read_document_property: 'utility',
    load_document: 'utility',
    upsert_document: 'utility',
    parse_document_body: 'utility',
    html_parse_basic: 'utility',
    write_object_to_document_body: 'utility',
    append_value_to_document: 'utility',
    validate_against_structure: 'utility',
    sandbox_tick_items: 'utility',
    sandbox_world_grid: 'utility',
    sandbox_available_cells: 'utility',
    sandbox_tick_pet: 'utility',
    sandbox_filter_items_by_type: 'utility',
    sandbox_nearest_item_by_type: 'utility',
    sandbox_closest_item: 'utility',
    sandbox_decision_intent: 'utility',
    sandbox_decision_move_to: 'utility',
    sandbox_starter_decision: 'utility',
    sandbox_pet_hunger: 'utility',
    sandbox_pet_energy: 'utility',
    sandbox_pet_cell: 'utility',
    sandbox_is_nearby8: 'utility',
    sandbox_first_nearby_food: 'utility',
    sandbox_first_food_world_order: 'utility',
    add_to_list: 'utility',
    add_ints: 'utility',
    add_days: 'utility',
    subtract_ints: 'utility',
    multiply_ints: 'utility',
    divide_ints: 'utility',
    modulo_ints: 'utility',
    min_ints: 'utility',
    max_ints: 'utility',
    basic_conditional: 'control',
    is_control: 'control',
    is_empty: 'control',
    gt_control: 'control',
    lt_control: 'control',
    gte_control: 'control',
    lte_control: 'control',
    and_control: 'control',
    or_control: 'control',
    xor_control: 'control',
    not_control: 'control',
    between_control: 'control',
    for_loop_control: 'control',
    for_loop_end_control: 'control',
};

export const WORKFLOW_PALETTE_COLORS: Record<string, string> = {
    string: '#38bdf8',
    list: '#f472b6',
    dictionary: '#e879f9',
    structure: '#a78bfa',
    document: '#2dd4bf',
    image: '#f43f5e',
    gmail: '#f97316',
    sandbox_behavior: '#34d399',
    decision_action: '#2dd4bf',
    sandbox_tick: '#2dd4bf',
    read_document_property: '#14b8a6',
    load_document: '#2dd4bf',
    upsert_document: '#14b8a6',
    parse_document_body: '#5eead4',
    html_parse_basic: '#65a30d',
    write_object_to_document_body: '#0d9488',
    append_value_to_document: '#0f766e',
    validate_against_structure: '#a78bfa',
    sandbox_tick_items: '#2dd4bf',
    sandbox_world_grid: '#5eead4',
    sandbox_available_cells: '#5eead4',
    sandbox_tick_pet: '#14b8a6',
    sandbox_filter_items_by_type: '#5eead4',
    sandbox_nearest_item_by_type: '#34d399',
    sandbox_closest_item: '#34d399',
    sandbox_decision_intent: '#10b981',
    sandbox_decision_move_to: '#059669',
    sandbox_starter_decision: '#059669',
    sandbox_pet_hunger: '#14b8a6',
    sandbox_pet_energy: '#0d9488',
    sandbox_pet_cell: '#0f766e',
    sandbox_is_nearby8: '#5eead4',
    sandbox_first_nearby_food: '#34d399',
    sandbox_first_food_world_order: '#2dd4bf',
    any: '#ffffff',
    workflow: '#14b8a6',
    simple_llm_call: '#8b5cf6',
    multimodal_llm: '#6366f1',
    text_to_speech: '#c4b5fd',
    transcribe_audio: '#4ade80',
    audio_file_input: '#22c55e',
    transcribe_file: '#16a34a',
    audio: '#c4b5fd',
    gmail_list_messages: '#ea4335',
    calendar_list_events: '#4285f4',
    fetch_url: '#0ea5e9',
    capture_url_snapshot: '#7c3aed',
    list_to_string: '#22d3ee',
    string_to_list: '#67e8f9',
    prepend_text: '#f59e0b',
    string_trunc: '#2dd4bf',
    message: '#c026d3',
    basic_conditional: '#10b981',
    is_control: '#06b6d4',
    is_empty: '#06b6d4',
    gt_control: '#0891b2',
    lt_control: '#0891b2',
    gte_control: '#0891b2',
    lte_control: '#0891b2',
    and_control: '#0d9488',
    or_control: '#0d9488',
    xor_control: '#0d9488',
    for_loop_control: '#059669',
    for_loop_end_control: '#047857',
    boolean: '#22c55e',
    int: '#f97316',
    datetime: '#0ea5e9',
    len_from_list: '#0ea5e9',
    random_item_from_list: '#ec4899',
    int_to_string: '#818cf8',
    list_item_by_index: '#a855f7',
    dictionary_value_by_key: '#9333ea',
    dictionary_set_value_by_key: '#7c3aed',
    add_to_list: '#d946ef',
    add_ints: '#2dd4bf',
    add_days: '#06b6d4',
    subtract_ints: '#14b8a6',
    multiply_ints: '#5eead4',
    divide_ints: '#0d9488',
    modulo_ints: '#f472b6',
    min_ints: '#34d399',
    max_ints: '#eab308',
    not_control: '#6366f1',
    between_control: '#c026d3',
    annotation_note: '#94a3b8',
    annotation_region: '#64748b',
};

/** React Flow editor-only types (handles not in API palette payloads). */
export const EDITOR_NODE_PALETTE_EXTRA: Record<string, string> = {
    start: '#6366f1',
    stop: '#f43f5e',
    trigger: '#94a3b8',
    signal: '#94a3b8',
};

/** Full fallback map for handle coloring in WorkflowEditor. */
export const DEFAULT_PALETTE_COLORS: Record<string, string> = {
    ...WORKFLOW_PALETTE_COLORS,
    ...EDITOR_NODE_PALETTE_EXTRA,
};

/**
 * Drop keys whose values equal shipped defaults in `WORKFLOW_PALETTE_COLORS`.
 * Stored palettes should stay sparse so optional step-family keys can apply;
 * otherwise every per-step key is always “set” and masks the family color.
 */
export function normalizeWorkflowPaletteColors(colors: Record<string, string>): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(colors)) {
        if (value === '' || value == null) continue;
        const base = WORKFLOW_PALETTE_COLORS[key];
        if (base !== undefined && value === base) continue;
        out[key] = value;
    }
    return out;
}

/**
 * Full explicit map for palette JSON export: every key in `WORKFLOW_PALETTE_COLORS`
 * is filled with the stored value or the shipped default (so “Specific step colors”
 * round-trip even when the editor never wrote unchanged keys into `form.colors`).
 * Optional family keys are included only when non-empty on `storedColors`.
 * Extra keys on `storedColors` are preserved.
 */
export function expandWorkflowPaletteColorsForExport(storedColors: Record<string, string>): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [key, defaultHex] of Object.entries(WORKFLOW_PALETTE_COLORS)) {
        const raw = storedColors[key];
        out[key] = raw != null && raw !== '' ? raw : defaultHex;
    }
    for (const key of WORKFLOW_PALETTE_FAMILY_KEYS) {
        const raw = storedColors[key];
        if (raw != null && raw !== '') {
            out[key] = raw;
        }
    }
    for (const [k, v] of Object.entries(storedColors)) {
        if (v != null && v !== '' && out[k] === undefined) {
            out[k] = v;
        }
    }
    return out;
}

/**
 * Resolve a hex color for handles/edges: specific key → optional step-family key
 * → built-in default for the key → `any`.
 */
export function resolveWorkflowPaletteColor(
    palette: Record<string, string> | undefined,
    handleKey: string
): string {
    const pal = palette ?? {};
    const spec = pal[handleKey];
    if (spec != null && spec !== '') return spec;
    const family = PALETTE_KEY_TO_FAMILY[handleKey];
    if (family != null) {
        const fam = pal[family];
        if (fam != null && fam !== '') return fam;
    }
    const def = DEFAULT_PALETTE_COLORS[handleKey];
    if (def != null && def !== '') return def;
    const anyPal = pal.any;
    if (anyPal != null && anyPal !== '') return anyPal;
    return DEFAULT_PALETTE_COLORS.any;
}
