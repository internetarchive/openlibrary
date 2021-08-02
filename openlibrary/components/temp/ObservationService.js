const OBSERVATIONS_SCHEMA = {
  observations: [
    {
      id: 1,
      label: "pace",
      description: "What is the pace of this book?",
      multi_choice: false,
      values: ["slow", "medium", "fast"]
    },
    {
      id: 2,
      label: "enjoyability",
      description: "How entertaining is this book?",
      multi_choice: false,
      values: [
        "not applicable",
        "very boring",
        "boring",
        "neither entertaining nor boring",
        "entertaining",
        "very entertaining"
      ]
    },
    {
      id: 3,
      label: "clarity",
      description: "How clearly is this book written?",
      multi_choice: false,
      values: [
        "not applicable",
        "very unclearly",
        "unclearly",
        "clearly",
        "very clearly"
      ]
    },
    {
      id: 4,
      label: "jargon",
      description: "How technical is the content?",
      multi_choice: false,
      values: [
        "not applicable",
        "not technical",
        "somewhat technical",
        "technical",
        "very technical"
      ]
    },
    {
      id: 5,
      label: "originality",
      description: "How original is this book?",
      multi_choice: false,
      values: [
        "not applicable",
        "very unoriginal",
        "somewhat unoriginal",
        "somewhat original",
        "very original"
      ]
    },
    {
      id: 6,
      label: "difficulty",
      description: "How advanced is the subject matter of this book?",
      multi_choice: false,
      values: [
        "not applicable",
        "requires domain expertise",
        "a lot of prior knowledge needed",
        "some prior knowledge needed",
        "no prior knowledge needed"
      ]
    },
    {
      id: 7,
      label: "usefulness",
      description: "How useful is the content of this book?",
      multi_choice: false,
      values: [
        "not applicable",
        "not useful",
        "somewhat useful",
        "useful",
        "very useful"
      ]
    },
    {
      id: 8,
      label: "coverage",
      description:
        "Does this book's content cover more breadth or depth of the subject matter?",
      multi_choice: false,
      values: [
        "not applicable",
        "much more deep",
        "somewhat more deep",
        "equally broad and deep",
        "somewhat more broad",
        "much more broad"
      ]
    },
    {
      id: 9,
      label: "objectivity",
      description: "Are there causes to question the accuracy of this book?",
      multi_choice: true,
      values: [
        "not applicable",
        "no, it seems accurate",
        "yes, it needs citations",
        "yes, it is inflammatory",
        "yes, it has typos",
        "yes, it is inaccurate",
        "yes, it is misleading",
        "yes, it is biased"
      ]
    },
    {
      id: 10,
      label: "genres",
      description: "What are the genres of this book?",
      multi_choice: true,
      values: [
        "sci-fi",
        "philosophy",
        "satire",
        "poetry",
        "memoir",
        "paranormal",
        "mystery",
        "humor",
        "horror",
        "fantasy",
        "drama",
        "crime",
        "graphical",
        "classic",
        "anthology",
        "action",
        "romance",
        "how-to",
        "encyclopedia",
        "dictionary",
        "technical",
        "reference",
        "textbook",
        "biographical"
      ]
    },
    {
      id: 11,
      label: "fictionality",
      description: "Is this book a work of fact or fiction?",
      multi_choice: false,
      values: ["nonfiction", "fiction", "biography"]
    },
    {
      id: 12,
      label: "audience",
      description: "What are the intended age groups for this book?",
      multi_choice: true,
      values: [
        "experts",
        "college",
        "high school",
        "elementary",
        "kindergarten",
        "baby",
        "general audiences"
      ]
    },
    {
      id: 13,
      label: "mood",
      description: "What are the moods of this book?",
      multi_choice: true,
      values: [
        "scientific",
        "dry",
        "emotional",
        "strange",
        "suspenseful",
        "sad",
        "dark",
        "lonely",
        "tense",
        "fearful",
        "angry",
        "hopeful",
        "lighthearted",
        "calm",
        "informative",
        "ominous",
        "mysterious",
        "romantic",
        "whimsical",
        "idyllic",
        "melancholy",
        "humorous",
        "gloomy",
        "reflective",
        "inspiring",
        "cheerful"
      ]
    }
  ]
};

// TODO: Does this need to be exported (or even exist at all)
// It may be moot as this is coming from a server call...
export const observations = OBSERVATIONS_SCHEMA["observations"];

function capitalizeObservations() {
  const result = observations;
  for (const item of result) {
    item.label = item.label[0].toUpperCase() + item.label.substring(1);

    for (const index in item.values) {
      item.values[index] = item.values[index][0].toUpperCase() + item.values[index].substring(1)
    }
  }

  return result;
}

export const presentableObservations = capitalizeObservations();
