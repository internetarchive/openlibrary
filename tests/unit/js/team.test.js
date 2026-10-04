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
    isLead,
    tenureSince,
    roleYears,
    personMatchesYear,
    allRoleYears,
    classifyTeam,
    slugify,
    assignSlugs,
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

describe('leads', () => {
    it('treats a current lead role as the Lead category', () => {
        expect(isLead(byName('Roni Bhakta'))).toBe(true); // Lenny Lead (current)
        expect(isLead(byName('Elizabeth Mays'))).toBe(true); // Comms Lead
        expect(isLead(byName('Bharat Kalluri'))).toBe(true); // Volunteer Lead
    });

    it('does not treat a PAST lead role as a current Lead', () => {
        // Ray & Lokesh led before becoming staff; their current role is staff.
        expect(isLead(byName('Ray Berger'))).toBe(false);
        expect(isLead(byName('Lokesh Dhakar'))).toBe(false);
        expect(isStaff(byName('Ray Berger'))).toBe(true);
    });

    it('pulls leads out of their cohort group in classifyTeam', () => {
        const g = classifyTeam(team, 2026);
        const leadNames = g.leads.map((p) => p.name);
        expect(leadNames).toContain('Roni Bhakta');
        expect(leadNames).toContain('Bharat Kalluri');
        // A lead must not also appear under fellows or volunteers.
        expect(g.currentFellows.map((p) => p.name)).not.toContain('Roni Bhakta');
        expect(g.volunteers.map((p) => p.name)).not.toContain('Bharat Kalluri');
    });
});

describe('tenureSince', () => {
    it('reports the current-role start year for active members', () => {
        expect(tenureSince(byName('Mek'), 2026)).toBe(2016);
        expect(tenureSince(byName('Drini Cami'), 2026)).toBe(2020);
        expect(tenureSince(byName('Ray Berger'), 2026)).toBe(2026); // staff as of 2026
    });

    it('omits a since-year for emeritus or past members', () => {
        expect(tenureSince(byName('Rebecca Shoptaw'), 2026)).toBeNull(); // staff emeritus
        expect(tenureSince(byName('Abbey Ripstra'), 2026)).toBeNull(); // 2023 fellow, past
    });
});

describe('year facet', () => {
    it('expands a single-year role to that year', () => {
        expect(roleYears(byName('Abbey Ripstra'), 2026).has(2023)).toBe(true);
        expect(roleYears(byName('Abbey Ripstra'), 2026).has(2022)).toBe(false);
    });

    it('expands an open-ended dated role through the current year', () => {
        const dated = { roles: [{ kind: 'staff', status: 'active', start: 2024, end: null }] };
        expect([...roleYears(dated, 2026)]).toEqual([2024, 2025, 2026]);
    });

    it('counts undated, still-active members in the current year', () => {
        // Current staff/volunteers carry an undated active role (no start year);
        // they must still surface when the current year is chosen.
        expect(personMatchesYear(byName('Mek'), 2026, 2026)).toBe(true);
        expect(personMatchesYear(byName('Alex Arasawa'), 2026, 2026)).toBe(true);
        // ...but an emeritus member with no dates is NOT assumed to be current.
        expect(personMatchesYear(byName('Aaron Swartz'), 2026, 2026)).toBe(false);
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
    it('partitions non-leads into staff/fellow/volunteer groups', () => {
        const groups = classifyTeam(team, 2026);
        const nonLeads = team.filter((p) => !isLead(p));
        const staff = nonLeads.filter(isStaff);
        const fellows = nonLeads.filter(isFellow);
        expect(groups.staffCurrent.length + groups.staffEmeritus.length).toBe(staff.length);
        expect(groups.currentFellows.length + groups.pastFellows.length).toBe(fellows.length);
        // Leads are disjoint from every cohort group.
        const cohorts = [
            ...groups.staffCurrent,
            ...groups.staffEmeritus,
            ...groups.currentFellows,
            ...groups.pastFellows,
            ...groups.volunteers,
        ];
        expect(cohorts.some((p) => groups.leads.includes(p))).toBe(false);
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

describe('slugs', () => {
    it('makes URL-safe, diacritic-free slugs', () => {
        expect(slugify('Ray Berger')).toBe('ray-berger');
        expect(slugify('Minh Huỳnh Khánh')).toBe('minh-huynh-khanh');
        expect(slugify('@Popcar')).toBe('popcar');
    });

    it('assigns a unique slug to every person', () => {
        const people = JSON.parse(JSON.stringify(team));
        assignSlugs(people);
        const slugs = people.map((p) => p.slug);
        expect(slugs.every(Boolean)).toBe(true);
        expect(new Set(slugs).size).toBe(slugs.length);
    });

    it('dedupes colliding slugs', () => {
        const people = [{ name: 'Sandy C.' }, { name: 'Sandy C' }];
        assignSlugs(people);
        expect(people[0].slug).toBe('sandy-c');
        expect(people[1].slug).toBe('sandy-c-2');
    });
});

describe('initTeamFilter (DOM wiring)', () => {
    const mountPage = (search = '/') => {
        window.history.replaceState({}, '', search);
        document.body.innerHTML = `
      <select id="role"><option value="All">All</option>
        <option value="staff">Staff</option><option value="lead">Leads</option>
        <option value="fellow">Fellows</option>
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

    it('labels fellows current/past relative to the selected year', () => {
        mountPage('/?role=fellow&year=2023');
        initTeamFilter();
        const subs = [...document.querySelectorAll('.subsectionSeparator')].map(
            (e) => e.textContent
        );
        // A 2023 fellow is "Current" when the view is scoped to 2023.
        expect(subs).toContain('Current');
    });

    it('renders a Leads section with the current leads', () => {
        mountPage();
        initTeamFilter();
        const headings = [...document.querySelectorAll('.sectionSeparator')].map(
            (e) => e.textContent
        );
        expect(headings).toContain('Leads');
        // Roni (Lenny Lead) should sit under Leads, not Fellows.
        const roni = document.getElementById('roni-bhakta');
        expect(roni).not.toBeNull();
    });

    it('filters to just leads via ?role=lead', () => {
        mountPage('/?role=lead');
        initTeamFilter();
        const headings = [...document.querySelectorAll('.sectionSeparator')].map(
            (e) => e.textContent
        );
        expect(headings).toEqual(['Leads']);
        expect(document.querySelectorAll('.teamCard').length).toBeGreaterThan(0);
    });

    it('shows each card\'s latest project and join year', () => {
        mountPage();
        initTeamFilter();
        const mek = document.getElementById('mek');
        expect(mek.querySelector('.description__tenure').textContent).toBe('Since 2016');
        // A member with a project shows its name.
        const roni = document.getElementById('roni-bhakta');
        expect(roni.querySelector('.description__project').textContent).toContain('Lenny');
    });

    it('makes the name a ?contributor= deep-link', () => {
        mountPage();
        initTeamFilter();
        const mek = document.getElementById('mek');
        // The name link is the direct-child anchor of the description (the photo
        // anchor lives in the photo container; the link icons are nested in a div).
        const nameLink = mek.querySelector('.teamCard__description > a');
        expect(nameLink.getAttribute('href')).toBe('?contributor=mek');
    });

    it('deep-links to a contributor via ?contributor= and highlights them', () => {
        mountPage('/?contributor=ray-berger');
        initTeamFilter();
        const card = document.getElementById('ray-berger');
        expect(card).not.toBeNull();
        expect(card.classList.contains('teamCard__container--highlighted')).toBe(true);
    });

    it('ignores a deep-link that collides with a filter control id', () => {
        mountPage('/?contributor=year');
        initTeamFilter();
        // #year is the dropdown, not a person card — it must not get highlighted.
        expect(
            document.getElementById('year').classList.contains('teamCard__container--highlighted')
        ).toBe(false);
    });

    it('reveals a filtered-out person when deep-linked', () => {
        // Jordan is a past (2025) fellow; a year filter would hide him, but a
        // deep-link should still surface and highlight him.
        mountPage('/?contributor=jordan-frederick&year=2026');
        initTeamFilter();
        const card = document.getElementById('jordan-frederick');
        expect(card).not.toBeNull();
        expect(card.classList.contains('teamCard__container--highlighted')).toBe(true);
    });
});
