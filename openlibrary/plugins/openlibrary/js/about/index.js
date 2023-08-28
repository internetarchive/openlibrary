console.log("Hooked up")

const team = [
    {
        name: "Drini",
        role: "Staff",
    },
    {
        name: "Jim",
        role: "Staff",
    },
    {
        name: "Aaron",
        role: "Staff, Emeritus",
    },
    {
        name: "Sam",
        role: "Fellow",
    },
    {
        name: "Abbey",
        role: "Fellow",
    },
    {
        name: "Jaye",
        role: "Volunteer",
    },
    {
        name: "Keita",
        role: "Volunteer",
    },
];

const staff = team.filter((person) => person.role.includes("Staff"));
const fellows = team.filter((person) => person.role.includes("Fellow"));
const volunteers = team.filter((person) =>
    person.role.includes("Volunteer")
);

const staffButton = document.getElementById("staffSort");
const fellowButton = document.getElementById("fellowSort");
const volunteerButton = document.getElementById("volunteerSort");
staffButton.addEventListener("click", () => console.log(staff));
fellowButton.addEventListener("click", () => console.log(fellows));
volunteerButton.addEventListener("click", () => console.log(volunteers));