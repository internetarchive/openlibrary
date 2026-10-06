import team from '../../../templates/about/team.json';
import { updateURLParameters } from './utils';

// ********************************* Pure helpers (role-history schema) *********************************
// A person's `roles` is a history list, most-recent first. Each entry is an object:
//   { kind: 'staff'|'fellow'|'volunteer', status?: 'active'|'emeritus',
//     title?, department?, lead?, program?, start?: year, end?: year|null }
// `end: null` means the role is ongoing. Section placement is derived from these objects.

// null (ongoing role) and undefined (field absent) are treated alike.
const isNil = (value) => value === null || value === undefined;

export const hasKind = (person, kind) =>
    (person.roles || []).some((role) => role.kind === kind);

export const isStaff = (person) => hasKind(person, 'staff');

// Fellows exclude anyone who became staff; volunteers exclude anyone who became a fellow.
export const isFellow = (person) =>
    hasKind(person, 'fellow') && !hasKind(person, 'staff');

export const isVolunteer = (person) =>
    hasKind(person, 'volunteer') && !hasKind(person, 'fellow');

// A current Lead = the person's most-recent (first) role carries the lead flag.
// Leads surface as their own category rather than under Staff/Fellows/Volunteers.
export const isLead = (person) => Boolean((person.roles || [])[0]?.lead);

export const isStaffEmeritus = (person) =>
    isStaff(person) &&
    (person.roles || []).some(
        (role) => role.kind === 'staff' && role.status === 'emeritus'
    );

export const isCurrentFellow = (person, year) =>
    isFellow(person) &&
    (person.roles || []).some(
        (role) => role.kind === 'fellow' && (isNil(role.end) || role.end === year)
    );

// Every calendar year a person held any role, for the Year facet.
export const roleYears = (person, currentYear) => {
    const years = new Set();
    (person.roles || []).forEach((role) => {
        if (isNil(role.start)) {
            // Undated but still-active/ongoing role (current staff, volunteers):
            // count it as the current year so the Year facet shows current members.
            if (isNil(role.end) && role.status === 'active') {
                years.add(currentYear);
            }
            return;
        }
        const end = isNil(role.end) ? currentYear : role.end;
        for (let y = role.start; y <= end; y++) {
            years.add(y);
        }
    });
    return years;
};

export const personMatchesYear = (person, year, currentYear) =>
    year === 'All' || roleYears(person, currentYear).has(Number(year));

// A URL-safe anchor slug for a person, e.g. "Minh Huỳnh Khánh" -> "minh-huynh-khanh".
export const slugify = (name) =>
    name
        .normalize('NFKD')
        .replace(/[̀-ͯ]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');

// Assign each person a unique `slug` (deduping collisions) for deep-linking.
export const assignSlugs = (people) => {
    const seen = new Set();
    people.forEach((person) => {
        const base = slugify(person.name) || 'member';
        let slug = base;
        let n = 2;
        while (seen.has(slug)) {
            slug = `${base}-${n++}`;
        }
        seen.add(slug);
        person.slug = slug;
    });
    return people;
};

// Every distinct year anyone held a role, newest first — powers the Year facet.
export const allRoleYears = (people, currentYear) => {
    const years = new Set();
    people.forEach((person) =>
        roleYears(person, currentYear).forEach((y) => years.add(y))
    );
    return [...years].sort((a, b) => b - a);
};

// Substring match preserved for departments (string list); '' matches everything.
const matchDepartment = (person, department) =>
    (person.departments || []).some((d) => d.includes(department));

export const classifyTeam = (people, year) => {
    // Leads are pulled into their own category; everyone else falls through to
    // their cohort (staff/fellow/volunteer).
    const leads = people.filter(isLead);
    const rest = people.filter((person) => !isLead(person));
    const staff = rest.filter(isStaff);
    return {
        leads,
        staffCurrent: staff.filter((p) => !isStaffEmeritus(p)),
        staffEmeritus: staff.filter(isStaffEmeritus),
        currentFellows: rest.filter((p) => isCurrentFellow(p, year)),
        pastFellows: rest.filter((p) => isFellow(p) && !isCurrentFellow(p, year)),
        volunteers: rest.filter(isVolunteer),
    };
};

// The year a member joined their current role, shown as "Since YYYY" on the card.
// Only for still-current, non-emeritus roles — "since" shouldn't read as ongoing
// for someone who has left or whose cohort year is in the past.
export const tenureSince = (person, currentYear) => {
    const role = (person.roles || [])[0];
    if (!role || isNil(role.start) || role.status === 'emeritus') {
        return null;
    }
    const current = isNil(role.end) || role.end >= currentYear;
    return current ? role.start : null;
};

export function initTeamFilter() {
    const currentYear = new Date().getFullYear();
    // Photos
    const default_profile_image =
    '../../../static/images/openlibrary-180x180.png';
    const bookUrlIcon = '../../../static/images/icons/icon_book-lg.png';
    const personalUrlIcon = '../../../static/images/globe-solid.svg';
    const initialSearchParams = new URL(window.location.href).searchParams;
    const initialRole = initialSearchParams.get('role') || 'All';
    const initialDepartment = initialSearchParams.get('department') || 'All';

    // Team sorted by last name
    const sortByLastName = (array) => {
        array.sort((a, b) => {
            const aName = a.name.split(' ');
            const bName = b.name.split(' ');
            const aLastName = aName[aName.length - 1];
            const bLastName = bName[bName.length - 1];
            if (aLastName < bLastName) {
                return -1;
            } else if (aLastName > bLastName) {
                return 1;
            } else {
                return 0;
            }
        });
    };
    sortByLastName(team);
    assignSlugs(team);

    // *************************************** Selectors and eventListeners ***************************************
    const roleFilter = document.getElementById('role');
    const departmentFilter = document.getElementById('department');
    const yearFilter = document.getElementById('year');
    const initialYear = initialSearchParams.get('year') || 'All';

    // Populate the Year dropdown from the data (newest first); "All" stays first.
    if (yearFilter) {
        allRoleYears(team, currentYear).forEach((year) => {
            const option = document.createElement('option');
            option.value = String(year);
            option.textContent = String(year);
            yearFilter.append(option);
        });
    }

    const applyFilters = () => {
        const role = roleFilter.value;
        const department = departmentFilter.value;
        const year = yearFilter ? yearFilter.value : 'All';
        filterTeam(role, department, year);
        updateURLParameters({ role, department, year });
    };

    roleFilter.value = initialRole;
    departmentFilter.value = initialDepartment;
    if (yearFilter) {
        yearFilter.value = initialYear;
    }
    roleFilter.addEventListener('change', applyFilters);
    departmentFilter.addEventListener('change', applyFilters);
    if (yearFilter) {
        yearFilter.addEventListener('change', applyFilters);
    }
    const cardsContainer = document.querySelector('.teamCards_container');

    // *************************************** Functions ***************************************
    const showError = () => {
        const noResults = document.createElement('h3');
        noResults.classList = 'noResults';
        noResults.textContent =
      'It looks like we don\'t have anyone with those specifications.';
        cardsContainer.append(noResults);
    };

    // Deep-link helpers. A contributor card has id=<slug>; ?contributor=<slug>
    // (or #<slug>) jumps to it, revealing it past any active filter.
    const findCard = (slug) => {
        const el = slug ? document.getElementById(slug) : null;
        return el && el.classList.contains('teamCard__container') ? el : null;
    };
    const revealCard = (slug) => {
        let card = findCard(slug);
        if (!card) {
            // Hidden by an active filter — show everyone, then retry.
            roleFilter.value = 'All';
            departmentFilter.value = 'All';
            if (yearFilter) {
                yearFilter.value = 'All';
            }
            filterTeam('All', 'All', 'All');
            card = findCard(slug);
        }
        return card;
    };
    const highlightCard = (card) => {
        cardsContainer
            .querySelectorAll('.teamCard__container--highlighted')
            .forEach((el) => el.classList.remove('teamCard__container--highlighted'));
        card.classList.add('teamCard__container--highlighted');
        if (card.scrollIntoView) {
            card.scrollIntoView({ block: 'center' });
        }
    };
    const goToContributor = (slug) => {
        const card = revealCard(slug);
        if (card) {
            highlightCard(card);
        }
    };

    const createCards = (array) => {
        array.map((member) => {
            // create
            const teamCardContainer = document.createElement('div');
            const teamCard = document.createElement('div');

            const teamCardPhotoContainer = document.createElement('div');
            const teamCardPhoto = document.createElement('img');

            const teamCardDescription = document.createElement('div');
            const nameLink = document.createElement('a');
            const memberName = document.createElement('h2');
            const memberTitle = document.createElement('h3');

            const descriptionLinks = document.createElement('div');

            //modify
            teamCardContainer.classList = 'teamCard__container';
            if (member.slug) {
                teamCardContainer.id = member.slug;
            }
            teamCard.classList = 'teamCard';

            teamCardPhotoContainer.classList = 'teamCard__photoContainer';
            teamCardPhoto.classList = 'teamCard__photo';
            teamCardPhoto.src = `${
                member.photo_path ? member.photo_path : default_profile_image
            }`;
            teamCardPhoto.alt = member.name;
            // The photo links to the member's Open Library profile; the name now
            // deep-links within this page (see below).
            if (member.ol_key) {
                const olProfile = document.createElement('a');
                olProfile.href = `https://openlibrary.org/people/${member.ol_key}`;
                olProfile.append(teamCardPhoto);
                teamCardPhotoContainer.append(olProfile);
            } else {
                teamCardPhotoContainer.append(teamCardPhoto);
            }

            teamCardDescription.classList.add('teamCard__description');
            // Clicking the name adds ?contributor=<slug> and jumps to this card.
            if (member.slug) {
                nameLink.href = `?contributor=${encodeURIComponent(member.slug)}`;
                nameLink.addEventListener('click', (e) => {
                    e.preventDefault();
                    updateURLParameters({ contributor: member.slug });
                    goToContributor(member.slug);
                });
            }
            member.name.length >= 18
                ? (memberName.classList = 'description__name--length-long')
                : (memberName.classList = 'description__name--length-short');

            memberName.textContent = `${member.name}`;
            memberTitle.classList = 'description__title';
            memberTitle.textContent = `${member.title}`;

            // Latest project, then the join year ("Since YYYY").
            const latestProject = (member.projects || [])[0];
            let memberProject;
            if (latestProject && latestProject.name) {
                memberProject = document.createElement('h4');
                memberProject.classList = 'description__project';
                if (latestProject.url) {
                    const projectLink = document.createElement('a');
                    projectLink.href = latestProject.url;
                    projectLink.textContent = latestProject.name;
                    memberProject.append(projectLink);
                } else {
                    memberProject.textContent = latestProject.name;
                }
            }
            const since = tenureSince(member, currentYear);
            let memberTenure;
            if (since) {
                memberTenure = document.createElement('p');
                memberTenure.classList = 'description__tenure';
                memberTenure.textContent = `Since ${since}`;
            }

            descriptionLinks.classList = 'description__links';
            if (member.personal_url) {
                const memberPersonalA = document.createElement('a');
                const memberPersonalImg = document.createElement('img');

                memberPersonalA.href = `${member.personal_url}`;
                memberPersonalImg.src = personalUrlIcon;
                memberPersonalImg.classList = 'links__site';

                memberPersonalA.append(memberPersonalImg);
                descriptionLinks.append(memberPersonalA);
            }

            if (member.favorite_book_url) {
                const memberBookA = document.createElement('a');
                const memberBookImg = document.createElement('img');

                memberBookA.href = `${member.favorite_book_url}`;
                memberBookImg.src = bookUrlIcon;
                memberBookImg.classList = 'links__book';

                memberBookA.append(memberBookImg);
                descriptionLinks.append(memberBookA);
            }

            // append (the photo was already placed in its container above)
            nameLink.append(memberName);
            teamCardDescription.append(nameLink, memberTitle);
            if (memberProject) {
                teamCardDescription.append(memberProject);
            }
            if (memberTenure) {
                teamCardDescription.append(memberTenure);
            }
            teamCardDescription.append(descriptionLinks);
            teamCard.append(teamCardPhotoContainer, teamCardDescription);
            teamCardContainer.append(teamCard);
            cardsContainer.append(teamCardContainer);
        });
    };

    const createSectionHeading = (text) => {
        const sectionSeparator = document.createElement('div');
        sectionSeparator.textContent = `${text}`;
        sectionSeparator.classList = 'sectionSeparator';
        cardsContainer.append(sectionSeparator);
    };

    const createsubSection = (array, text) => {
        const subsectionSeparator = document.createElement('div');
        subsectionSeparator.textContent = `${text}`;
        subsectionSeparator.classList = 'subsectionSeparator';
        cardsContainer.append(subsectionSeparator);
        createCards(array);
    };

    const filterTeam = (role, department, year) => {
        cardsContainer.textContent = '';
        // Year and department narrow the pool; role then chooses which sections show.
        let people = team.filter((person) =>
            personMatchesYear(person, year, currentYear)
        );
        if (department !== 'All') {
            people = people.filter((person) => matchDepartment(person, department));
        }
        // When a specific year is chosen, "current" fellows are those current in
        // that year, not today — so the Current/Past labels read correctly.
        const classYear = year === 'All' ? currentYear : Number(year);
        const groups = classifyTeam(people, classYear);
        const anyShown =
      groups.leads.length ||
      groups.staffCurrent.length ||
      groups.staffEmeritus.length ||
      groups.currentFellows.length ||
      groups.pastFellows.length ||
      groups.volunteers.length;

        if (role === 'All') {
            if (groups.staffCurrent.length || groups.staffEmeritus.length) {
                createSectionHeading('Staff');
                groups.staffCurrent.length &&
          createsubSection(groups.staffCurrent, 'Current');
                groups.staffEmeritus.length &&
          createsubSection(groups.staffEmeritus, 'Emeritus');
            }
            if (groups.leads.length) {
                createSectionHeading('Leads');
                createCards(groups.leads);
            }
            if (groups.currentFellows.length || groups.pastFellows.length) {
                createSectionHeading('Fellows');
                groups.currentFellows.length &&
          createsubSection(groups.currentFellows, 'Current');
                groups.pastFellows.length &&
          createsubSection(groups.pastFellows, 'Past');
            }
            if (groups.volunteers.length) {
                createSectionHeading('Volunteers');
                createCards(groups.volunteers);
            }
            !anyShown && showError();
        } else {
            createSectionHeading(capitalize(role));
            if (role === 'lead') {
                groups.leads.length ? createCards(groups.leads) : showError();
            } else if (role === 'volunteer') {
                groups.volunteers.length
                    ? createCards(groups.volunteers)
                    : showError();
            } else if (role === 'staff') {
                groups.staffCurrent.length &&
          createsubSection(groups.staffCurrent, 'Current');
                groups.staffEmeritus.length &&
          createsubSection(groups.staffEmeritus, 'Emeritus');
                !groups.staffCurrent.length &&
          !groups.staffEmeritus.length &&
          showError();
            } else {
                groups.currentFellows.length &&
          createsubSection(groups.currentFellows, 'Current');
                groups.pastFellows.length &&
          createsubSection(groups.pastFellows, 'Past');
                !groups.currentFellows.length &&
          !groups.pastFellows.length &&
          showError();
            }
        }
    };

    const capitalize = (text) => {
        const firstLetter = text[0].toUpperCase();
        if (text === 'fellow' || text === 'volunteer' || text === 'lead') {
            return `${firstLetter + text.slice(1)}s`;
        } else {
            return firstLetter + text.slice(1);
        }
    };

    // Deep-link on load from ?contributor=<slug> or #<slug>.
    const focusContributor = () => {
        const target =
      initialSearchParams.get('contributor') ||
      (window.location.hash
          ? decodeURIComponent(window.location.hash.slice(1))
          : '');
        if (target) {
            goToContributor(target);
        }
    };

    // on page load
    filterTeam(initialRole, initialDepartment, initialYear);
    focusContributor();
}
