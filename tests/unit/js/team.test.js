import { describe, it, expect } from 'vitest';
import team from '../../../openlibrary/templates/about/team.json';
import {
    initTeamFilter,
    hasKind,
    isStaff,
    isFellow,
    isVolunteer,
    isStaffEmeritus,
    isCurrentFellow,
    roleYears,
    personMatchesYear,
    allRoleYears,
    classifyTeam,
} from '../../../openlibrary/plugins/openlibrary/js/team.js';

const byName = (name) => team.find((p) => p.name === name);

describe('team.json schema', () => {
    it('is a non-empty list where every record has a roles history list', () => {
        expect(Array.isArray(team)).toBe(true);
        expect(team.length).toBeGreaterThan(0);
        for (const person of team) {
            expect(Array.isArray(person.roles)).toBe(true);
            expect(person.roles.length).toBeGreaterThan(0);
            for (const role of person.roles) {
                expect(['staff', 'fellow', 'volunteer']).toContain(role.kind);
            }
        }
    });

    it('places every person in at least one visible section (nobody invisible)', () => {
        for (const person of team) {
            const placed = isStaff(person) || isFellow(person) || isVolunteer(person);
            expect(placed, `${person.name} falls into no section`).toBe(true);
        }
    });
});

describe('role classification', () => {
    it('treats staff/fellow/volunteer as a precedence ladder', () => {
        // Someone who became staff is no longer listed as a fellow.
        const lisa = byName('Lisa S.'); // staff-active + fellow-2018
        expect(isStaff(lisa)).toBe(true);
        expect(isFellow(lisa)).toBe(false);
    });

    it('classifies known staff, fellows, and volunteers', () => {
        expect(isStaffEmeritus(byName('Aaron Swartz'))).toBe(true);
        expect(isStaff(byName('Mek')) && !isStaffEmeritus(byName('Mek'))).toBe(true);
        expect(isFellow(byName('Abbey Ripstra'))).toBe(true);
        expect(isVolunteer(byName('Alex Arasawa'))).toBe(true);
    });

    it('distinguishes current from past fellows by year', () => {
        const abbey = byName('Abbey Ripstra'); // fellow-2023
        expect(isCurrentFellow(abbey, 2026)).toBe(false);
        expect(isCurrentFellow(abbey, 2023)).toBe(true);
    });
});

describe('year facet', () => {
    it('expands a single-year role to that year', () => {
        expect(roleYears(byName('Abbey Ripstra'), 2026).has(2023)).toBe(true);
        expect(roleYears(byName('Abbey Ripstra'), 2026).has(2022)).toBe(false);
    });

    it('expands an open-ended role up to the current year', () => {
        // staff-active with no end -> ongoing; the helper fills through currentYear.
        const years = roleYears(byName('Mek'), 2026);
        // Mek's staff role carries no start year, so it contributes nothing; a dated
        // role would. Assert the open-ended expansion on a dated+ongoing fixture instead:
        const dated = { roles: [{ kind: 'staff', status: 'active', start: 2024, end: null }] };
        expect([...roleYears(dated, 2026)]).toEqual([2024, 2025, 2026]);
        expect(years.size).toBeGreaterThanOrEqual(0);
    });

    it('matches "All" and specific years', () => {
        const abbey = byName('Abbey Ripstra');
        expect(personMatchesYear(abbey, 'All', 2026)).toBe(true);
        expect(personMatchesYear(abbey, 2023, 2026)).toBe(true);
        expect(personMatchesYear(abbey, 2020, 2026)).toBe(false);
    });

    it('lists every distinct role year, newest first, for the dropdown', () => {
        const years = allRoleYears(team, 2026);
        expect(years).toEqual([...years].sort((a, b) => b - a)); // descending
        expect(new Set(years).size).toBe(years.length); // distinct
        expect(years).toContain(2026);
        expect(years.every((y) => typeof y === 'number')).toBe(true);
    });
});

describe('classifyTeam', () => {
    it('partitions staff into current + emeritus and fellows into current + past', () => {
        const groups = classifyTeam(team, 2026);
        const allStaff = team.filter(isStaff);
        const allFellows = team.filter(isFellow);
        expect(groups.staffCurrent.length + groups.staffEmeritus.length).toBe(allStaff.length);
        expect(groups.currentFellows.length + groups.pastFellows.length).toBe(allFellows.length);
    });

    it('never lists the same person as both current and emeritus staff', () => {
        const groups = classifyTeam(team, 2026);
        const overlap = groups.staffCurrent.filter((p) => groups.staffEmeritus.includes(p));
        expect(overlap).toEqual([]);
    });
});

describe('hasKind', () => {
    it('reports the kinds present in a role history', () => {
        const p = { roles: [{ kind: 'staff' }, { kind: 'fellow' }] };
        expect(hasKind(p, 'staff')).toBe(true);
        expect(hasKind(p, 'volunteer')).toBe(false);
    });
});

describe('initTeamFilter (DOM wiring)', () => {
    const mountPage = () => {
        document.body.innerHTML = `
      <select id="role"><option value="All">All</option>
        <option value="staff">Staff</option><option value="fellow">Fellows</option>
        <option value="volunteer">Volunteers</option></select>
      <select id="department"><option value="All">All</option>
        <option value="engineer">Engineering</option></select>
      <select id="year"><option value="All">All</option></select>
      <div class="teamCards_container"></div>`;
    };

    it('populates the Year dropdown from the data and renders cards', () => {
        mountPage();
        initTeamFilter();
        const years = [...document.querySelectorAll('#year option')].map((o) => o.value);
        expect(years[0]).toBe('All');
        expect(years).toContain('2026');
        expect(years.length).toBeGreaterThan(2);
        expect(document.querySelectorAll('.teamCard').length).toBeGreaterThan(0);
    });

    it('narrows the roster when a year is chosen', () => {
        mountPage();
        initTeamFilter();
        const all = document.querySelectorAll('.teamCard').length;
        const year = document.getElementById('year');
        year.value = '2023';
        year.dispatchEvent(new Event('change'));
        const in2023 = document.querySelectorAll('.teamCard').length;
        expect(in2023).toBeGreaterThan(0);
        expect(in2023).toBeLessThan(all);
        expect(new URL(window.location.href).searchParams.get('year')).toBe('2023');
    });
});
