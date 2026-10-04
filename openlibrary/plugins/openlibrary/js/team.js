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
        if (isNil(role.start)) return;
        const end = isNil(role.end) ? currentYear : role.end;
        for (let y = role.start; y <= end; y++) {
            years.add(y);
        }
    });
    return years;
};

export const personMatchesYear = (person, year, currentYear) =>
    year === 'All' || roleYears(person, currentYear).has(Number(year));

// Substring match preserved for departments (string list); '' matches everything.
const matchDepartment = (person, department) =>
    (person.departments || []).some((d) => d.includes(department));

export const classifyTeam = (people, year) => {
    const staff = people.filter(isStaff);
    return {
        staffCurrent: staff.filter((p) => !isStaffEmeritus(p)),
        staffEmeritus: staff.filter(isStaffEmeritus),
        currentFellows: people.filter((p) => isCurrentFellow(p, year)),
        pastFellows: people.filter((p) => isFellow(p) && !isCurrentFellow(p, year)),
        volunteers: people.filter(isVolunteer),
    };
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

    // *************************************** Team sorted by role ***************************************
    const { staffCurrent, staffEmeritus, currentFellows, pastFellows, volunteers } =
    classifyTeam(team, currentYear);

    // *************************************** Selectors and eventListeners ***************************************
    const roleFilter = document.getElementById('role');
    const departmentFilter = document.getElementById('department');
    roleFilter.value = initialRole;
    roleFilter.addEventListener('change', (e) =>   {
        filterTeam(e.target.value, departmentFilter.value);
        updateURLParameters({
            role: e.target.value,
            department: departmentFilter.value
        });
    });
    departmentFilter.value = initialDepartment;
    departmentFilter.addEventListener('change', (e) => {
        filterTeam(roleFilter.value, e.target.value);
        updateURLParameters({
            role: roleFilter.value,
            department: departmentFilter.value
        });
    });
    const cardsContainer = document.querySelector('.teamCards_container');

    // *************************************** Functions ***************************************
    const showError = () => {
        const noResults = document.createElement('h3');
        noResults.classList = 'noResults';
        noResults.textContent =
      'It looks like we don\'t have anyone with those specifications.';
        cardsContainer.append(noResults);
    };

    const createCards = (array) => {
        array.map((member) => {
            // create
            const teamCardContainer = document.createElement('div');
            const teamCard = document.createElement('div');

            const teamCardPhotoContainer = document.createElement('div');
            const teamCardPhoto = document.createElement('img');

            const teamCardDescription = document.createElement('div');
            const memberOlLink = document.createElement('a');
            const memberName = document.createElement('h2');
            const memberTitle = document.createElement('h3');

            const descriptionLinks = document.createElement('div');

            //modify
            teamCardContainer.classList = 'teamCard__container';
            teamCard.classList = 'teamCard';

            teamCardPhotoContainer.classList = 'teamCard__photoContainer';
            teamCardPhoto.classList = 'teamCard__photo';
            teamCardPhoto.src = `${
                member.photo_path ? member.photo_path : default_profile_image
            }`;
            teamCardPhoto.alt = member.name;

            teamCardDescription.classList.add('teamCard__description');
            if (member.ol_key) {
                memberOlLink.href = `https://openlibrary.org/people/${member.ol_key}`;
            }
            member.name.length >= 18
                ? (memberName.classList = 'description__name--length-long')
                : (memberName.classList = 'description__name--length-short');

            memberName.textContent = `${member.name}`;
            memberTitle.classList = 'description__title';
            memberTitle.textContent = `${member.title}`;

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

            // append
            teamCardPhotoContainer.append(teamCardPhoto);
            memberOlLink.append(memberName);
            teamCardDescription.append(
                memberOlLink,
                memberTitle,
                descriptionLinks
            );
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

    const filterTeam = (role, department) => {
        cardsContainer.textContent = '';
        // **************************************** default sort *****************************************
        if (role === 'All' && department === 'All') {
            createSectionHeading('Staff');
            createsubSection(staffCurrent, 'Current');
            createsubSection(staffEmeritus, 'Emeritus');

            createSectionHeading('Fellows');
            createsubSection(currentFellows, 'Current');
            createsubSection(pastFellows, 'Past');

            createSectionHeading('Volunteers');
            createCards(volunteers);
        }
        // ************************************* sort by department ***************************************
        else if (role === 'All' && department !== 'All') {
            const filteredTeam = team.filter((person) =>
                matchDepartment(person, department)
            );

            const groups = classifyTeam(filteredTeam, currentYear);

            const staff = filteredTeam.filter(isStaff);
            staff.length && createSectionHeading('Staff');
            groups.staffCurrent.length &&
        createsubSection(groups.staffCurrent, 'Current');
            groups.staffEmeritus.length &&
        createsubSection(groups.staffEmeritus, 'Emeritus');

            const fellows = filteredTeam.filter(isFellow);
            fellows.length && createSectionHeading('Fellows');
            groups.currentFellows.length &&
        createsubSection(groups.currentFellows, 'Current');
            groups.pastFellows.length &&
        createsubSection(groups.pastFellows, 'Past');

            groups.volunteers.length && createSectionHeading('Volunteers');
            createCards(groups.volunteers);
        }
        // ****************************** sort by role and/or department *******************************
        else {
            department === 'All' ? (department = '') : department;
            createSectionHeading(capitalize(role));
            if (role === 'volunteer') {
                const filteredVolunteers = volunteers.filter((person) =>
                    matchDepartment(person, department)
                );
                filteredVolunteers.length !== 0
                    ? createCards(filteredVolunteers)
                    : showError();
            } else if (role === 'staff') {
                const filteredCurrentStaff = staffCurrent.filter((person) =>
                    matchDepartment(person, department)
                );
                const filteredStaffEmeritus = staffEmeritus.filter((person) =>
                    matchDepartment(person, department)
                );
                filteredCurrentStaff.length &&
          createsubSection(filteredCurrentStaff, 'Current');
                filteredStaffEmeritus.length &&
          createsubSection(filteredStaffEmeritus, 'Emeritus');
                !filteredCurrentStaff.length &&
          !filteredStaffEmeritus.length &&
          showError();
            } else {
                const filteredCurrentFellows = currentFellows.filter((person) =>
                    matchDepartment(person, department)
                );
                const filteredPastFellows = pastFellows.filter((person) =>
                    matchDepartment(person, department)
                );
                filteredCurrentFellows.length &&
          createsubSection(filteredCurrentFellows, 'Current');
                filteredPastFellows.length &&
          createsubSection(filteredPastFellows, 'Past');
                !filteredCurrentFellows.length &&
          !filteredPastFellows.length &&
          showError();
            }
        }
    };

    const capitalize = (text) => {
        const firstLetter = text[0].toUpperCase();
        if (text === 'fellow' || text === 'volunteer') {
            return `${firstLetter + text.slice(1)}s`;
        } else {
            return firstLetter + text.slice(1);
        }
    };

    // on page load
    filterTeam(initialRole, initialDepartment);
}
