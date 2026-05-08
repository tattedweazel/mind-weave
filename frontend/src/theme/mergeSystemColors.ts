/**
 * Merge order for resolved theme: shipped defaults → active system palette → User.settings.system_colors.
 */

import type { SystemColorsMode } from './defaults';

export function mergeResolvedSystemColors(
    defaults: SystemColorsMode,
    presetPartial: Partial<SystemColorsMode> | undefined,
    userPartial: Partial<SystemColorsMode> | undefined,
): SystemColorsMode {
    return { ...defaults, ...presetPartial, ...userPartial };
}
