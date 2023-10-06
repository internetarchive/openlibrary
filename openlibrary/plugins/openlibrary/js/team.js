import team from '../../../templates/about/team.json';
export function initTeamFilter() {
    // Photos
    const default_profile_image =
		'../../../static/images/openlibrary-180x180.png';
    const bookUrlIcon = '../../../static/images/icons/icon_book-lg.png';
    const personalUrlIcon = '../../../static/images/globe-solid.svg';

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
    }
    sortByLastName(team)

    // Match a substring in each person's role
    const matchSubstring = (array, substring) => {
        return array.some(item => item.includes(substring))
    }

    // Team sorted by role
    const staff = team.filter((person) => matchSubstring(person.roles, 'staff'));
    const fellows = team.filter((person) => matchSubstring(person.roles, 'fellow') && !matchSubstring(person.roles, 'staff'))
    const volunteers = team.filter((person) =>
        matchSubstring(person.roles, 'volunteer') && !matchSubstring(person.roles, 'fellow')
    );


    // Selectors and eventListeners
    const roleFilter = document.getElementById('role');
    const departmentFilter = document.getElementById('department');
    roleFilter.addEventListener('change', (e) =>
        filterTeam(e.target.value, departmentFilter.value)
    );
    departmentFilter.addEventListener('change', (e) =>
        filterTeam(roleFilter.value, e.target.value)
    );
    const cardsContainer = document.querySelector('.teamCards_container');

    // Functions
    const createCards = (array) => {
        if (array.length === 0) {
            const noResults = document.createElement('h3');
            noResults.classList = 'noResults'
            noResults.innerHTML =
				'It looks like we don\'t have anyone with those specifications.';
            cardsContainer.append(noResults);
        } else {
            array.map((member) => {
                // create
                const teamCardContainer = document.createElement('div');
                const teamCard = document.createElement('div');

                const teamCardPhotoContainer = document.createElement('div');
                const teamCardPhoto = document.createElement('img');

                const teamCardDescription = document.createElement('div');
                const memberOlLink = document.createElement('a');
                const memberName = document.createElement('h2');
                // const memberRole = document.createElement('h4');
                // const memberDepartment = document.createElement('h3');
                const memberTitle = document.createElement('h3')

                const descriptionLinks = document.createElement('div');

                //modify
                teamCardContainer.classList =('teamCard__container');
                teamCard.classList = 'teamCard';

                teamCardPhotoContainer.classList = 'teamCard__photoContainer';
                teamCardPhoto.classList = 'teamCard__photo';
                teamCardPhoto.src = `${
                    member.photo_path
                        ? member.photo_path
                        : default_profile_image
                }`;

                teamCardDescription.classList.add('teamCard__description');
                if (member.ol_key) {
                    memberOlLink.href = `https://openlibrary.org/people/${member.ol_key}`;
                }
                member.name.length >= 18
                    ? (memberName.classList = 'description__name--length-long')
                    : (memberName.classList =
							'description__name--length-short');

                memberName.innerHTML = `${member.name}`;
                // memberRole.classList = 'description__role';
                // memberRole.innerHTML = `${role}`;
                // memberDepartment.classList = 'description__department';
                // memberDepartment.innerHTML = `${member.departments}`;
                memberTitle.classList = 'description__title'
                memberTitle.innerHTML = `${member.title}`

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

                if (member.favorite_book_url !== '') {
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
                    // memberRole,
                    // memberDepartment,
                    memberTitle,
                    descriptionLinks
                );
                teamCard.append(teamCardPhotoContainer,teamCardDescription);
                teamCardContainer.append(teamCard);
                cardsContainer.append(teamCardContainer);
            });
        }
    };

    const createSection = (array, text) => {
        const sectionSeparator = document.createElement('div');
        sectionSeparator.innerHTML = `${text}`
        sectionSeparator.classList = 'sectionSeparator'
        cardsContainer.append(sectionSeparator);
        createCards(array);
    };

    const filterTeam = (role, department) => {
        cardsContainer.innerHTML = '';
        // **************************************** default sort *****************************************
        if (role === 'All' && department === 'All') {
            createSection(staff, 'Staff');
            createSection(fellows, 'Fellows');
            createSection(volunteers, 'Volunteers');
        }
        // ************************************* sort by department ***************************************
        else if (role === 'All' && department !== 'All') {
            role = '';
            const filteredTeam = team.filter(
                (person) =>
                    matchSubstring(person.roles, role) && matchSubstring(person.departments, department)
            );

            const staff = filteredTeam.filter((person) => matchSubstring(person.roles, 'staff'));
            const fellows = filteredTeam.filter((person) => matchSubstring(person.roles, 'fellow') && !matchSubstring(person.roles, 'staff'))
            const volunteers = filteredTeam.filter((person) => matchSubstring(person.roles, 'volunteer') && !matchSubstring(person.roles, 'fellow'));

            staff.length !== 0 && createSection(staff, 'Staff')
            fellows.length !== 0 && createSection(fellows, 'Fellows')
            volunteers.length !== 0 && createSection(volunteers, 'Volunteers')
        }
        // ****************************** sort by role and/or department *******************************
        else {
            department === 'All' ? department = '' : department
            const filteredTeam = role === 'fellow' ? team.filter(
                (person) =>
                    matchSubstring(person.roles, role) && !matchSubstring(person.roles, 'staff') && matchSubstring(person.departments, department)
            ) : team.filter(
                (person) =>
                    matchSubstring(person.roles, role) && matchSubstring(person.departments, department)
            );
            createSection(filteredTeam, capitalize(role))
        }
    };

    const capitalize = (text) => {
        const firstLetter = text[0].toUpperCase()
        if (text === 'fellow' || text === 'volunteer') {
            return `${firstLetter + text.slice(1)}s`
        }
        else {
            return firstLetter + text.slice(1)
        }
    }

    // on page load
    createSection(staff, 'Staff');
    createSection(fellows, 'Fellows');
    createSection(volunteers, 'Volunteers');
}
