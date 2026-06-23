import type { Page } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';

/**
 * Axe configuration for WCAG 2.1 AA scans.
 * Matches the target adopted 2026-06-23.
 */
const WCAG_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

/**
 * Returns an AxeBuilder pre-configured for WCAG 2.1 AA scans.
 * Caller can chain .exclude(), .disableRules(), etc. before .analyze().
 */
export function buildAxeScanner(page: Page): AxeBuilder {
    return new AxeBuilder({ page }).withTags(WCAG_AA_TAGS);
}

export interface ViolationSummary {
    id: string;
    impact: string | null | undefined;
    nodeCount: number;
    help: string;
}

/**
 * Extracts a compact summary from axe violation results for logging/annotations.
 */
export function summarizeViolations(
    violations: Awaited<ReturnType<AxeBuilder['analyze']>>['violations'],
): ViolationSummary[] {
    return violations.map(v => ({
        id: v.id,
        impact: v.impact,
        nodeCount: v.nodes.length,
        help: v.help,
    }));
}

/**
 * Formats violations as a compact string for test annotations.
 * Example: "3 violations: color-contrast(79,serious), frame-title(10,serious)"
 */
export function formatViolationAnnotation(
    violations: Awaited<ReturnType<AxeBuilder['analyze']>>['violations'],
): string {
    if (violations.length === 0) return '0 violations';
    const items = violations
        .map(v => `${v.id}(${v.nodes.length},${v.impact ?? 'unknown'})`)
        .join(', ');
    return `${violations.length} violations: ${items}`;
}
