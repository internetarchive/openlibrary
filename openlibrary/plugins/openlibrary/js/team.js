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

    // Team sorted by role
    const staff = team.filter((person) => person.roles.includes('Staff'));
    const fellows = team.filter((person) => person['roles'].includes('Fellow'));
    const volunteers = team.filter((person) =>
        person['roles'].includes('Volunteer')
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
                const memberRole = document.createElement('h4');
                const memberDepartment = document.createElement('h3');

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
                memberOlLink.href = `${
                    member.ol_user_url ? member.ol_user_url : ''
                }`;
                member.name.length >= 18
                    ? (memberName.classList = 'description__name--length-long')
                    : (memberName.classList =
							'description__name--length-short');

                memberName.innerHTML = `${member.name}`;
                memberRole.classList = 'description__role';
                memberRole.innerHTML = `${member.roles}`;
                memberDepartment.classList = 'description__department';
                memberDepartment.innerHTML = `${member.departments}`;

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
                    memberRole,
                    memberDepartment,
                    descriptionLinks
                );
                teamCard.append(teamCardPhotoContainer,teamCardDescription);
                teamCardContainer.append(teamCard);
                cardsContainer.append(teamCardContainer);
            });
        }
    };

    const createSection = (array) => {
        const sectionSeparator = document.createElement('div');
        array === staff
            ? (sectionSeparator.classList = 'hidden')
            : (sectionSeparator.classList = 'sectionSeparator');
        cardsContainer.append(sectionSeparator);
        createCards(array);
    };

    const filterTeam = (role, department) => {
        cardsContainer.innerHTML = '';
        if (role === 'All' && department === 'All') {
            createSection(staff);
            createSection(fellows);
            createSection(volunteers);
        } else if (role === 'All' && department !== 'All') {
            role = '';
            const filteredTeam = team.filter(
                (person) =>
                    person.roles.includes(role) &&
                    person.departments.includes(department)
            );

            const staff = filteredTeam.filter((person) => person.roles.includes('Staff'))
            const fellows = filteredTeam.filter((person) => person.roles.includes('Fellow'))
            const volunteers = filteredTeam.filter((person) => person.roles.includes('Volunteer'))

            staff.length !== 0 && createSection(staff)
            fellows.length !== 0 && createSection(fellows)
            volunteers.length !== 0 && createSection(volunteers)
        } else if ((department === 'All') & (role !== 'All')) {
            department = '';
            const filteredTeam = team.filter(
                (person) =>
                    person.roles.includes(role) &&
                    person.departments.includes(department)
            );
            createCards(filteredTeam);
        } else {
            const filteredTeam = team.filter(
                (person) =>
                    person.roles.includes(role) &&
                    person.departments.includes(department)
            );
            createCards(filteredTeam);
        }
    };

    // on page load
    createSection(staff);
    createSection(fellows);
    createSection(volunteers);
}
