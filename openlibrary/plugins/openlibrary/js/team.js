export function initTeamFilter() {
console.log("Hooked up")

const team = [
    {
        name: "Drini",
        role: "Staff",
		department: "Engineering"
    },
    {
        name: "Jim",
        role: "Staff",
		department: "Communications"
    },
    {
        name: "Aaron",
        role: "Staff, Emeritus",
		department: "Communications"
    },
    {
        name: "Sam",
        role: "Fellow",
		department: "Communications"
    },
    {
        name: "Abbey",
        role: "Fellow",
		department: "Design"
    },
    {
        name: "Jaye",
        role: "Volunteer",
		department: "Engineering"
    },
    {
        name: "Keita",
        role: "Volunteer",
		department: "Librarianship"
    },
];

const staff = team.filter((person) => person.role.includes("Staff"));
const fellows = team.filter((person) => person.role.includes("Fellow"));
const volunteers = team.filter((person) => person.role.includes("Volunteer"));
const cardsContainer = document.querySelector(".cards_container");
cardsContainer.className += " testing";

const filterTeam = (role, department) => {
	if (role == "All") {
		role = "";
	} else if (department == "All") {
		department = "";
	}

	const filteredTeam = team.filter(
		(person) =>
			person.role.includes(role) && person.department.includes(department)
	);
	console.log(filteredTeam);

	filteredTeam.map((member) => {
		const teamCardContainer = document.createElement("p");
		const teamCard = document.createElement("div");
		const teamCardPhotoContainer = document.createElement("div");
		const teamCardPhoto = document.createElement("img");

		// teamCardContainer.innerHTML = "$member.get('name','')";
		// cardsContainer.append(teamCardContainer);
	});
};

const roleFilter = document.getElementById("role");
const departmentFilter = document.getElementById("department");

roleFilter.addEventListener("change", (e) =>
	filterTeam(e.target.value, departmentFilter.value)
);
departmentFilter.addEventListener("change", (e) =>
	filterTeam(roleFilter.value, e.target.value)
);

}