


<script>
export default {
    emits: ['sample'],

    data() {
        return {
            selectedValue: '',
            sample1: '',
            sample2: '',
            sample3: '',
            placeholder: ''

        }
    },
    mounted() {
        this.sample1 = this.$refs.sample1Ref.textContent;
        this.sample2 = this.$refs.sample2Ref.textContent;
        this.sample3 = this.$refs.sample3Ref.textContent;
    },
    watch: {
        usedSample(newValue){
            this.$emit('sample', newValue)
        }
    },
    computed: {
        usedSample(){
            const dict = {sample1: this.sample1, sample2: this.sample2, sample3: this.sample3}
            return dict[this.selectedValue]
        }
    }


}

</script>


<template>
<div>


    <label>Sample Data: <select v-model="selectedValue">

      <option>Choose sample...</option>
      <option value="sample1">TED’s 2018 winter reading list</option>
      <option value="sample2">GoodRead's best books of 1995</option>
      <option value="sample3">Holocaust Wikipedia citations</option>
    </select></label>






<pre ref="sample1Ref" hidden>

ideas.ted.com
Explore ideas worth spreading
TED Logo
TED’s winter reading list: 78 feel-good books

    Tech
    Business
    Arts + Design
    Science
    We humans

Search Icon
Search for:
We humans
TED’s winter reading list: 78 feel-good books
Dec 6, 2018
Share This Idea

    Click to share on Facebook (Opens in new window)
    Click to share on Twitter (Opens in new window)
    Click to share on LinkedIn (Opens in new window)
    Click to share on Pinterest (Opens in new window)

iStock
Enthusiastic recommendations for reads that will provide you with abundant reasons to rejoice, reflect or recharge, as suggested by TED speakers and TED-Ed educators.
If you’re searching for some calm

The Peace of Wild Things: And Other Poems by Wendell Berry
This little book of poetry is my current morning dose of calm, and I use it like a meditation if I’m feeling stressed about the day ahead. The most famous verse in it is the title poem, which never fails to bring me back from our tech-driven, fast-paced world into memories of beautiful forest walks. Through this volume, I’m enjoying discovering other work by this wonderful poet, who writes: “For a time, I rest in the grace of the world, and am free.”
— Suzie Sheehy (TED talk: The case for curiosity-driven research)

The Rain in Portugal by Billy Collins (TED talk: Two poems about what dogs think — probably)
Collins is by far my favorite poet. His words fill me with such ease and warmth, and they never fail to put me in a better, heightened mood. I always feel like his poems help me to see the world, rather than just pass through it blindly. I could have picked any volume of his work, but this — his latest — is a great place for people to start.
— Luke Sital-Singh (TED performance: “Afterneath” / “Killing Me”)

Bells in Winter by Czeslaw Milosz
This slim book of poetry brings moments of intense wonder about the unknowableness of the human condition. Some of these poems calm me like a drink of cold, clear water. That there is someone like Milosz, who can understand and distill the human experience in this way, helps make our modern social chaos recede.
— Linda Elkins-Tanton (TED-Ed lesson: Why is NASA sending a spacecraft to a metal world?)

Zen Shorts by Jon J. Muth
My husband and I read this illustrated children’s book to my daughter many times, but I think he and I learned more from it than she did! It imparts important life lessons like: “good” and “bad” life events don’t exist — what seems like a good life circumstance can have bad consequences, and what seems like a bad situation can lead to something positive. I practice what I learned from these inspiring stories daily.
— Mara Mintzer (TED talk: How kids can help design cities)
If you’d like to be closer to the people in your life

Your Body Is Your Brain: Leverage Your Somatic Intelligence To Find Purpose, Build Resilience, Deepen Relationships and Lead More Powerfully by Amanda Blake
I love a read that leaves me believing I can change by practicing simple steps, and this book is all that. Blake teaches us how to tap into our most powerful intelligence — namely, posture, gestures and sensations — and truly live from our authentic power.
— Tammy Lally (TED talk: Let’s get honest about our money problems)

Peaceful Parent, Happy Siblings: How to Stop the Fighting and Raise Friends for Life by Dr. Laura Markham
Markham has been such a companion to me and my wife in our parenting journey. While raising children is perhaps the biggest gift, it is not without its challenges. This book provides actionable tools and advice, all steeped in robust research, that I find myself excited to put into practice. That’s rare with self-help books!
— Vinay Shandal (TED talk: How conscious investors can turn up the heat and make companies change)

Mistakes Were Made (But Not By Me): Why We Justify Foolish Beliefs, Bad Decisions, and Hurtful Acts by Carol Tavris and Elliot Aronson
This book forces me to be self-reflective and recognize when cognitive dissonance enters my decision-making process. Citing numerous historical examples in which this psychological phenomenon has negatively impacted outcomes, Tavris and Aronson brilliantly show the reader how we can identify dissonance in our choices, ultimately helping you make better decisions and foster better relationships.
— Kelly Richmond-Pope (TED talk: How whistle-blowers shape history)

Taking the Work Out of Networking: An Introvert’s Guide to Making Connections That Count by Karen Wickre
Who knew connecting with others for one’s career could be so authentic, observational and reciprocal? In this practical, delightful read, Wickre reveals a whole new kind of networking for our increasingly transactional digital world. Full of insights and helpful tips, especially regarding social media, this is the perfect book for anyone in the midst of a career transition or considering one. (Read an excerpt from the book here.)
— Chip Conley (TED talk: What baby boomers can learn from millennials at work — and vice versa)
If you want a book that makes you feel all your feelings

Americanah by Chimamanda Ngozi Adichie (TED talk: The danger of a single story)
This was the first book I read as an adult that made me feel understood. Navigating the multiple cultures that you’re a part of — as an immigrant or first-generation person in the West — is quite an endeavor. Doing this while carrying your Blackness and Africanness, in addition to maintaining your humanity, is a journey. Adichie does this with sagacious humor in her novel.
— Michael Rain (TED talk: What it’s like to be the child of immigrants)

The Boys in the Boat: Nine Americans and Their Epic Quest for Gold at the 1936 Berlin Olympics by Daniel James Brown
I loved The Boys in the Boat. It’s the inspiring true story of the University of Washington crew team which ended up, against all odds, competing in the 1936 Olympic Games. In this book, the facts are as fun as fiction.
— Finn Lützow-Holm Myrstad (TED talk: How tech companies deceive you into giving up your data and privacy)

The Apocalypse of Elena Mendoza by Shaun David Hutchinson
In this novel, Elena is born from a mother who is a virgin, but Elena’s life is anything but religious. When a Starbucks logo commands her to heal a gunshot victim — who also happens to be her crush — she does it and then sets off a chain reaction. I love how this book highlights the way we must choose to do good again and again. It isn’t necessarily inherent within us, but we can choose goodness anyway.
— Dawn Wacek (TED talk: A librarian’s case against overdue fines)

We, The Drowned by Carsten Jensen
This novel is so immersive you don’t want it ever to end. A vivid historical epic spanning four generations, it’s told from the point of view of a whole town — a small Danish sailing community tackling the challenges of emergent globalization and war. It’s as exciting as any thriller, as involving as any psychological drama, and as moving as the deepest romance.
— Özlem Sara Cekic (TED talk: Why I have coffee with people who send me hate mail)

Air Traffic: A Memoir of Ambition and Manhood in America by Gregory Pardlo
Air Traffic was written by one of my mentors, the Pulitzer Prize-winning poet Pardlo. It helped me deal with the complicated range of emotions that I struggled with after I lost my father last year. This memoir is about a difficult relationship between a father and son, and it shows us love in a form that we rarely see displayed openly. It’s work to try to understand and accept a complex person while still seeing them in all their humanity — including their anguish and their ugliness.
— Michael Rain (TED talk: What it’s like to be the child of immigrants)

The Storied Life of A. J. Fikry by Gabrielle Zevin
This is a beautiful novel about grief and love, and finding meaning after loss. A.J. owns a bookstore — another thing to love — and he has recently lost his pregnant wife to a terrible accident. He withdraws into his work, but even that doesn’t bring him joy anymore. When a mysterious package is left on his doorstep, A.J. is pushed to begin seeing the world, and his place in it, in a new light.
— Dawn Wacek (TED talk: A librarian’s case against overdue fines)
If you just want a reason to smile

Dirk Gently’s Holistic Detective Agency by Douglas Adams
This book makes me giggle out loud every time. Overshadowed by Adams’ more famous work, the Dirk Gently novels are a delightful read. They’re chock full of his trademark humorous writing and lovable character creations, like the Electric Monk (a labor-saving device that believes things for you so that you don’t have to) and a bored horse. The horse is my favorite.
— Kate Darling (TED talk: Why we have an emotional connection to robots)

Kitchen Confidential: Adventures in the Culinary Underbelly by Anthony Bourdain
The patron saint of chefs and travel tragically committed suicide earlier this year. Listen to the audio version of the memoir that made him famous; it’s read aloud by the man himself. It will make you miss him all over again, but you’ll also laugh and smile for what he once gave us.
— Prosanta Chakrabarty (TED talk: Four billion years of evolution in six minutes)

A Walk in the Woods: Rediscovering America on the Appalachian Trail by Bill Bryson
This comical true tale of Bryson’s misadventures as he hikes the Appalachian Trail left me with a stomach ache from laughing out loud. It inspired me to take on new adventures — no matter how ill prepared I might be!
— Lucy Marcil (TED talk: Why doctors are offering free tax prep in their waiting rooms)

The Essential Haiku: Versions of Bashō, Buson & Issa edited by Robert Hass
Whenever I want a good laugh, I browse this compilation of haikus by several of the Japanese masters. Descriptive phrases like “Morning breeze riffling the caterpillar’s hair” and “Year after year, a monkey’s face, on the monkey’s face” capture nature like I’ve never seen elsewhere. Their appreciation for the mundane and the way in which they find hilarity in the natural world makes for a book to be read out loud — whether you’re around the campfire or when you’re enjoying time with friends and family.
— Rebecca Tarvin (TED-Ed lesson: Why don’t poisonous animals poison themselves?)

How To Be Idle: A Loafer’s Manifesto by Tom Hodgkinson
This is a funny, eye-opening guide to why and how we are living is making us so miserable, but we can’t even say that, let alone object. This book explains how we were not always so work obsessed; instead, work was integrated into our lives, which were more than what we did to earn money. Plus, there’s a great chapter on why we do hangovers all wrong.
— Simone George (TED talk with Mark Pollock: A love letter to realism in a time of grief)

How to Be a Woman by Caitlin Moran
This nonfiction book made me laugh hard, as it hand-held me through some of the thinking around feminism and gendered roles. It’s a classic, really, and a great gateway drug for anyone who thinks that diving into the incredible canon of feminist writing might not be for them. It is. Let Moran walk you in.
— Simone George (TED talk with Mark Pollock: A love letter to realism in a time of grief)

The Misadventures of Awkward Black Girl by Issa Rae
Not really a memoir but more a collection of essays, this book made me laugh out loud on one page and then question some of my assumptions and beliefs on another. I particularly connected with it, because Rae is around my age and some of the coming-of-age stories that she tells revolve around the new technologies (AOL chat rooms!) that we were all exploring — resulting in both our edification and corruption — in the mid-to-late ‘90s.
— Elizabeth Cawein (TED talk: How to build a thriving music scene in your city)

The Code of the Woosters by P.G. Wodehouse
Joseph Connolly, in summarizing his 2004 biography of Wodehouse, wrote the following: “Wodehouse was not deep. He had no message. He was merely one of the greatest writers in the history of literature. Behind the happy face there lived a happy man.” While you’re reading this novel about Bertie Wooster’s attempt to track down a Dutch cow-creamer you, too, will be happy.
— Stephen Webb (TED talk: Where are all the aliens?)
If you want to learn more about humans and our collective ingenuity

Sapiens: A Brief History of Humankind by Yuval Noah Harari (TED talk: Why fascism is so tempting — and how your data could power it)
This book is full of useful information about the past and present of humanity. I loved how open-minded it was, and I was very excited to learn the little details that drive the way we behave.
— Lina Marieth Hoyos (TED-Ed lesson: What is the coldest thing in the world?)

The Innovators: How a Group of Hackers, Geniuses, and Geeks Created the Digital Revolution by Walter Isaacson
If you want to learn about the history of the digital revolution, this book is for you. It takes readers on a tour through the stories of several innovators and creators of devices and developments that are very useful in our present-day lives. Traveling from the ideas of Ada Lovelace to Steve Jobs, this book shows us how they took a step beyond conventional thinking with their revolutionary ideas.
— Lina Marieth Hoyos (TED-Ed lesson: What is the coldest thing in the world?)

One Good Turn by Witold Rybczynski
This nonfiction book is aimed at the technologically minded but also at anyone who has an interest in the historical development of civilization. Around the turn of the millennium, the author was asked to find and write about the most useful tool of the previous 1,000 years. I won’t spoil what it was — you need to read it to find out, but it’s certainly something that none of us can do without.
— Ian Firth (TED talk: Bridges should be beautiful)
If you’re fascinated about the inner lives of well-known people

Minority Leader: How to Lead from the Outside and Make Change by Stacey Abrams (TED talk: 3 questions to ask yourself about everything you do)
I work in government affairs, and the last thing I enjoy reading for pleasure are books by politicians. However, this book is different on so many levels and is a must-read — whether you’re a political junkie or just someone seeking inspiration to chart your own course. I instantly related to and was inspired by Abrams’s candid struggles to overcome self-doubt and embrace the full range of her abilities as a talented woman of color. Her writing is candid, eloquent, familiar, funny and highly digestible. I found myself nodding, smiling, dog-earing pages, and taking deep inhalations to digest her inspiring wisdom.
— Nikki Clifton (TED talk: 3 ways business can fight sex trafficking)

Grant by Ron Chernow
Chernow — who also gave us the famed biography of Alexander Hamilton — will be the featured speaker at the White House Correspondents Dinner in April 2019, in a break from the tradition of having a comedian. But after reading Grant, I can understand why. This biography tells us how an alcoholic, gullible sad-sack became one of the the most famous soldiers in US history as well as the civil-rights championing 18th President — it has all the elements of the next great Lin-Manuel Miranda musical.
— Prosanta Chakrabarty (TED talk: Four billion years of evolution in six minutes)

Alibaba: The House That Jack Ma Built by Duncan Clark
I enjoyed this very inspiring book about the personal and professional life of Alibaba founder Jack Ma. Ma’s likable and easy-going personality makes the book very inspiring and fun to read, while also providing interesting insights as to how he managed to establish one of the highest-valued companies in China and the world.
— Pierre Barreau (TED talk: How AI could compose a personalized soundtrack to your life)

Becoming by Michelle Obama
In this memoir, First Lady Michelle Obama is elegant and unapologetic about living your truth, being of great public service, dreaming big, and never giving up. She is eloquent, raw and real in describing her personal experiences and how she found her voice. Her account of public service — both in the White House and in her private life — is truly remarkable, and I’m excited to see this book encourage others to “become” the next, greater version of themselves.
— Darieth Chisholm (TED talk: How revenge porn turns lives upside down)
If you’re interested in all things related to home

Entertaining with Vegetables: A Recipe Collection for Modern Home Cooks to Make Lovely and Delicious Food with Produce by Chadwick Boyd
Every kitchen needs this inspiring cookbook. I am “almost” a vegetarian because of it. Each recipe is so creative, packed full of Imagination and flavor, flavor and more flavor. You can feel Chadwick’s love for food and connection on every page.
— Tammy Lally (TED talk: Let’s get honest about our money problems)

Strudel, Noodles & Dumplings: The New Taste of German Cooking by Anja Dunk
I love an avocado as much as the next guy, but nothing makes me happier than a proper, hearty, home-cooked meal — that’s what Dunk’s cooking is all about. She’s written my favorite kind of cookbook with the perfect blend of originality and familiarity. Every recipe looks as achievable as it looks delicious, and it’s all written up with a warmth and honesty that can come only from a real person doing real life.
— Luke Sital-Singh (TED performance: “Afterneath” / “Killing Me”)

The Life-Changing Magic of Tidying Up: The Japanese Art of Decluttering and Organizing by Marie Kondo
At first glance, one would think this book is only about organizing your closet (and closet organization is discussed), but what I learned is that the same principles applied to organizing your home can apply to your calendar, your finances and your business relationships. After applying the Kondo principles to my entire life, I regained valuable time which led to greater mental clarity. This book taught me a mindset that’s led to extreme happiness and productivity.
— Kelly Richmond-Pope (TED talk: How whistle-blowers shape history)

This book helps you practice living with freedom from material possessions. It’s a very practical, actionable guide to decluttering your life and helping you trade chaos for clarity.
— Alex Edmans (TED talk: What to trust in a “post-truth” world)

Joyful: The Surprising Power of Ordinary Things to Create Extraordinary Happiness by Ingrid Fetell Lee (TED talk: Where joy hides and how to find it)
I really enjoyed this really well-written and easy-to-read book. It talks about how we can make the world a much better place if we’d only build environments which make us smile and bring joy to our lives, instead of the usual, mundane gray spaces that so many of us are forced to live and work in. Every designer, architect, politician, civil servant and, in fact, everyone should read this book and start to make a difference in the patch where they live. (Read an excerpt here.)
— Ian Firth (TED talk: Bridges should be beautiful)
If you want to enjoy a book with your favorite little person

Rosie Revere, Engineer by Andrea Beaty

This is a favorite read of mine — and of my two-year-old and and my four-year-old. It offers uplifting lessons in creative problem solving, perseverance with trial and error, and innovation, and I love how it ties into history — young Rosie’s namesake Aunt helped build airplanes during WWII and serves as inspiration and cheerleader for the next generation. It also has great whimsical illustrations.
— Daniel Kraft (TED talk: The pharmacy of the future? Personalized pills, 3D printed at home)

Does It Fart? The Definitive Field Guide to Animal Flatulence by Nick Caruso and Dani Rabiotti
When I showed this book’s cover page to my seven-year-old daughter, she covered her mouth and giggled — and then she called her sister over to flip through the book. The text is fun and full of facts for anyone of all ages. It covers animal farters (actual and alleged) from herrings to humans, even unicorns. (The authors say that these creatures would fart if they were real, basing their contention on an Arabian oryx or the extinct Elasmotherium, the so-called “Siberian unicorn”). If you’re looking for a new way to get natural history knowledge that you didn’t know you needed, this book is for you.
— Prosanta Chakrabarty (TED talk: Four billion years of evolution in six minutes)

The Monster Book of Switzerland by Jeanne Darling
This is a fantastic and beautifully illustrated children’s book with lots of enjoyable monsters and trivia about Switzerland, where I spent most of my life. And the author just happens to be my mother, who started writing popular Swiss children’s books as a 70-year-old retired teacher! It makes me feel both at home and truly inspired to follow my dreams.
— Kate Darling (TED talk: Why we have an emotional connection to robots)

It’s Okay to Be Different by Todd Parr
Parr delivers an impactful message in an impactful way. This children’s book empowers kids to be who they are, accept who others are, and do so without judgment. I read this with my toddler son at least once a week.
— Vinay Shandal (TED talk: How conscious investors can turn up the heat and make companies change)
If you thrill to people’s survival stories, both real and fictional

Eva Luna by Isabel Allende (TED talk: Tales of passion)
When I was 17, I read this novel, which was the first book I ever read by Allende. Eva Luna is orphaned at an early age in a unidentified country in Latin America, and her story highlights some of the political issues post-World War II. It opened my eyes to magical realism and to the region as a whole.
— Finn Lützow-Holm Myrstad (TED talk: How tech companies deceive you into giving up your data and privacy)

The Examined Life: How We Lose and Find Ourselves by Stephen Grosz
This book s a collection of deeply moving stories of self-discovery by psychoanalyst Grosz. His writing about therapy has been described as “like a combination of Chekhov and Oliver Sacks.” Whether it’s finding and keeping love, facing trauma in a family history, or confronting the most sensitive personal or professional vulnerabilities, this book brings hope by showing that humans have the capacity to heal — even bloom — when living with life’s most painful emotional scars.
— Alexandra Sacks (TED talk: A new way to think about the transition to motherhood)

Unbroken: A World War II Story of Survival, Resilience and Redemption by Laura Hillenbrand
I hesitated reading this nonfiction book after it was given to me by a friend, because it seemed like more of a feel-good story than what usually attracts me. Wow, was I mistaken! I found this book about the life of Louis Zamperini to be incredibly uplifting and almost impossible to put down. Hillenbrand does an elegant job of capturing details that make his story come alive without weighing down the amazing narrative of this real-life hero, who was an Olympic distance runner, an Air Force pilot in WWII, and a Japanese POW, among many other things. This beautifully told story of the life of Zamperini inspired me to be more than who I am.
— Ben Cort (TED talk: What commercialization is doing to cannabis)

News of the World by Paulette Jiles
I’m a sucker for books today that help us rethink — and rewrite — our founding myths of the American West. Jiles’ novel takes a harrowing tale of a German girl captured by the Kiowa Indians and spins it into a feel-good yarn about humanity’s capacity for empathy.
— Chip Colwell (TED talk: Why museums are returning cultural treasures)

Heavy: An American Memoir by Kiese Laymon
Laymon’s memoir hit home for me as he lives in Oxford, Mississippi, which is within 100 miles of my own creative work base. The author grapples with childhood traumas and coming-of-age revelations and emotions, all of which served to define the man he has become. This book, which is in the second person, is written as an engaging confession to his brilliantly damaged mother. It’s transformative, empowering and soulful.
— tobacco brown (TED talk: What gardening taught me about life)
If you want to regain a sense of wonder about the world

Black Hole: How an Idea Abandoned by Newtonians, Hated by Einstein, and Gambled On by Hawking Became Loved by Marcia Bartusiak
Not many people know that the story which led to the discovery of black holes is as odd as the astronomical objects. From the late 17th-century publication of the gravitational theory by Isaac Newton, it took almost three centuries to accept that, when it comes to black holes, the apparently impossible is real. Black holes are collapsed objects that possess infinite density. In this exciting scientific adventure, Bartusiak describes the emergence of the crazy ideas behind these objects. This book will teach you that sometimes the impossible can become true.
— Fabio Pacucci (TED-Ed lesson: Could the earth by swallowed by a black hole?)

The Feynman Lectures on Physics by Richard Feynman, Robert B. Leighton and Matthew Sands
It may seem strange to pick a three-volume collection of physics lectures and try and sell it as feel-good reading, but as I can confirm, you can return to these famous “red books” time and again and, each time, find insight, ingenuity and inspiration.
— Stephen Webb (TED talk: Where are all the aliens?)

Seeing Science: An Illustrated Guide to the Wonders of the Universe by Iris Gottlieb
While I use music and sound, Gottlieb uses the universal language of visual art to understand and share the elegant beauty of the world around us. Equal parts fascinating and whimsical, this book tells the stories of scientific wonders big and small, with many frame-worthy pages along the way. It shows the potential rewards of fearlessly following your curiosity and imagination, wherever it leads.
— Matt Russo (TED talk: What does the universe sound like? A musical tour)

The Feather Thief: Beauty, Obsession, and the Natural History Heist of the Century by Kirk Wallace Johnson
This nonfiction book is part mystery, part natural history, and part jaw-dropping mirror of our modern society. Johnson does an amazing job of seeking to understand the role of natural history collections and explaining how misinterpreting their role can lead people astray. He follows one man’s obsession with the obscure and ancient art of fly-tying and how that led him to break into a museum to steal priceless specimens. If you love nature or museums, this crime will chill you to the bone.
— Prosanta Chakrabarty (TED talk: Four billion years of evolution in six minutes)

The Best American Science and Nature Writing 2018, edited by Sam Kean
The science of the soul. Tiny jumping spiders who can see the moon. Firestorms. Fantastic beasts. You can’t go wrong with the latest installment of this annual series — it will leave you filled with questions, knowledge, motivation and wonder!
— Chip Colwell (TED talk: Why museums are returning cultural treasures)

H is for Hawk by Helen MacDonald
I really enjoyed this beautifully written memoir, a mixture of philosophy with the author coming to terms with the death of her father and her insightful story about training a pet goshawk. It’s a great holiday present for someone, particularly if they love birds of prey.
— Ian Firth (TED talk: Bridges should be beautiful)

The Skeptic’s Guide to the Universe: How to Tell What’s Really Real In a World Increasingly Full of Fake by Steven Novella
Novella is right up there with Carl Sagan as people who taught me the joy and humility that comes with understanding how our brains actually work (or don’t!) in our quest to understand the cosmos and ourselves. This is the ultimate guide to critical thinking, with all the charm and irreverence that Steve and the other “Rogues” bring to their weekly podcast of the same name. As the subtitle suggests, this book comes at a time when we need it most.
— Matt Russo (TED talk: What does the universe sound like? A musical tour)

Pale Blue Dot: A Vision of the Human Future in Space by Carl Sagan
This book highlights our place in the universe in a very uplifting way. The earth, this place we call our home, is just a tiny spot in the vastness of space, and the book shows us that the small “pale blue dot” where we live is a small dot full of life and love.
— Lina Marieth Hoyos (TED-Ed lesson: What is the coldest thing in the world?)

The Invention of Nature: Alexander von Humboldt’s New World by Andrea Wulf
This is a deeply human story of our drive to explore, as told through the biography of polymath, naturalist and geographer Alexander von Humboldt. This nonfiction book inspired me to build a cyanometer to measure the blueness of the sky, to channel the courage that he used to climb unclimbable mountains, and to imagine how scientists and humanists can invent a better world.
— Linda Elkins-Tanton (TED-Ed lesson: Why is NASA sending a spacecraft to a metal world?)
If creativity and art are what get you out of bed in the morning

Jonathan Livingston Seagull by Richard Bach
This is a short read, but this classic novel touches on creativity, learning, freedom from conformity, and flying, one of my favorite elements. I first read it when I was in my early 20s and then re-read it years later. It’s served as a touchtone to finding and flying through one’s own passions and paths.
— Daniel Kraft (TED talk: The pharmacy of the future? Personalized pills, 3D printed at home)

Engineering and the Mind’s Eye by Eugene S. Ferguson
Although this isn’t a new book — it was published in 1994 — it reminds us that the innate creativity in the mind of an engineer is what matters, not his or her ability to do math. Creativity lies at the heart of all good engineering, and this excellent book shows why so much of the content in our university education programs is wrongly focused, particularly so in this day and age.
— Ian Firth (TED talk: Bridges should be beautiful)

The Ensemble by Aja Gabel
I liked this novel about a string quartet because it offers such a great portrait of ambition and friendship that’s created by the love of music. It illustrates how a common love for art can shape a beautiful bond that goes through failures and successes, yet never breaks.
— Pierre Barreau (TED talk: How AI could compose a personalized soundtrack to your life)

Dreaming the Beatles: The Love Story of One Band and the Whole World by Rob Sheffield
I am a self-described Rob Sheffield superfan, and while I would love most anything he wrote, this is particularly special. Even the Beatles aficionado will find new insight in this nonfiction book, which explores not just the Beatles but also the world that revolves around them, unpacking the way each generation has discovered and claimed the band as its own. Dreaming is as much about the Beatles as it is about pop culture, pop music, fandom, obsession and the power of our emotional connection to art.
— Elizabeth Cawein (TED talk: How to build a thriving music scene in your city)

Feel Free: Essays by Zadie Smith
Feel Free is a collection of intriguing essays that speak about modern-day, socio-political, newsworthy topics, including the movie Get Out and pop icon Justin Bieber. Smith is an inventive free thinker — she’s viscerally, audibly and visually refreshing. Through her writing, she offers readers the opportunity to learn to trust their own voices.
— tobacco brown (TED talk: What gardening taught me about life)
If you want to feel fired up to change the world

Rage Becomes Her: The Power of Women’s Anger by Soraya Chemaly
NPR has named this book as one of the best in 2018. It challenges the conventional wisdom that anger, especially coming from women, is not a valid expression of emotion. Rage explores the importance of anger for women in these troubling political times as we take to the streets and occupy more political offices, and it reveals how stiffing our anger is part of a systematic pattern of power and oppression to silence women and prevent gender equality. (Read an excerpt from the book here.)
— Laura L. Dunn (TED talk: It’s time for the law to protect victims of gender violence)

Poems, Protest and a Dream by Sor Juana Inés de la Cruz
This anthology of writings by the 17th-century Mexican nun — among the best poets in the Spanish language — shows the degree to which the #MeToo movement has deep historical roots. Sor Juana, whose fight with the male ecclesiastical establishment ultimately forced her to take a vow of silence, writes in such pungent explosions of clarity, it’s as if her thoughts were ready-made for the age of Twitter. Almost 350 years after her death, she is at once a calming force and an inspiration to fight against censorship and for true gender equality.
— Ilan Stavans (TED-Ed lesson: Why you should read Don Quixote?)

Women Who Run With the Wolves by Clarissa Pinkola Estes
This book weaves together lessons about our psyche and feminine energy from the author’s psychoanalytic background, as told through stories like the girl with the matchbox. It’s packed with beautifully told lessons about how we can grow our awareness of ourselves — both our light and shadow, both our conscious and subconscious — so that we can contact our inner feminine power and unleash it.
— Rola Hallam (TED talk: The doctors, nurses and aid workers rebuilding Syria)

A Grace Paley Reader: Stories, Essays, Poetry by Grace Paley
Paley’s soothing voice — at times, it feels as if her rhythmic English is an effortless translation of the Yiddish once used by many Jewish immigrants — has the capacity to make the reader enter an alternative universe, one in which empathy is the law of the land. Yet she was also a tireless activist who saw writing as a way to denounce those who abuse power. Her legacy makes one grateful that literature, even though it may appear insignificant to some, is what actually remains.
— Ilan Stavans (TED-Ed lesson: Why you should read Don Quixote?)
If you yearn to visit other worlds

Lilith by George MacDonald
Anyone who inspired such household names as J.R.R. Tolkien and C.S. Lewis to write — as MacDonald indeed did — should be carefully considered. MacDonald wrote several remarkable novels and stories, but at the top of my list is this masterpiece. His ability to convey deep truth through allegory has been often mimicked but seldom duplicated. This book changed my entire worldview and brought me great hope. My guess is that Lilith will make a MacDonald fan out of many of the people who pick it up.
— Ben Cort (TED talk: What commercialization is doing to cannabis)

From the Earth to the Moon by Jules Verne
In this classic 1865 novel, there’s everything you’d ever need to be inspired: curiosity towards the unknown, challenge, impossible travels, faith in scientific knowledge, and unshakable courage. It also anticipated the lunar landing by more than a century. I read this book when I was 12 years old, and it has greatly inspired my efforts to reach for the stars.
— Fabio Pacucci (TED-Ed lesson: Could the earth by swallowed by a black hole?)

To Say Nothing of the Dog by Connie Willis
Science fiction isn’t a genre usually associated with comfort reads, but Willis is an expert at exploring speculative concepts through lovable, quirky characters. Here, her time-travelling Oxford University professors become embroiled in a Victorian-era farce of mistaken identity, temporal paradox and love.
— Stephen Webb (TED talk: Where are all the aliens?)
If you’d like to engage in some spiritual exploration

The Spiral Staircase: My Climb Out of Darkness by Karen Armstrong (TED talk: Let’s revive the Golden Rule)
This memoir is about Armstrong’s journey to find God after she joins a convent at 17 and the unexpected path that she finds herself on. I found this book an inspiring and intriguing look at one woman’s path, the human condition and spirituality.
— Lucy Marcil (TED talk: Why doctors are offering free tax prep in their waiting rooms)

The Art of Happiness: A Handbook for Living by the Dalai Lama
We all want to be happy, but so few of us know how or even what the word really means. In this profound book, the Tibetan leader shares practical suggestions on how to do the inner self-work necessary for cultivating it and also the exceptional wisdom that we can only find true happiness when that work is dedicated to the benefit of other beings. In other words, our happiness is intrinsically linked to the happiness of others — true happiness is when we work hard, internally and externally, to make it a reality for all of us.
— Rola Hallam (TED talk: The doctors, nurses and aid workers rebuilding Syria)

Calm My Anxious Heart: A Woman’s Guide to Finding Contentment by Linda Dillow
I am a mother and, therefore, I’m prone to limitless worry. As a divorced, single mom, I went through periods where my worry turned to unproductive anxiousness. A good friend recommended this book as a way to reconnect to my spiritual upbringing, and it set me on a path to thrive — rather than simply survive — through life challenges. This guide has inspired me to seek contentment, instead of certainty, and to have a deeper connection to my faith.
— Nikki Clifton (TED talk: 3 ways business can fight sex trafficking)

The Rhythm of Life: Living Every Day with Passion and Purpose by Matthew Kelly
Kelly, founder of the Dynamic Catholic Institute, inspires you to lead a life filled with passion and purpose. He offers strategies for discovering your desires, identifying your unique talents and becoming the best version of yourself.
— Christine Porath (TED talk: Why being respectful to your coworkers is good for business)

Why Buddhism is True: The Science and Philosophy of Meditation and Enlightenment by Robert Wright (TED talk: The evolution of compassion)
Wright writes with a combination of humility and wisdom, summarizing the best research on the science behind Buddhist practices in an approachable manner. This book makes me feel hopeful that there is a life beyond our human neuroses, no matter what form they take, and it’s a great read for both skeptics of meditation and experienced meditators.
— Mara Mintzer (TED talk: How kids can help design cities)
If you’re a visual reader

Art Forms in Nature by Ernst Haeckel
Haeckel is one of my favorite biologists from the 19th century. He is famous in part for the incorrect idea that animals go through several stages of evolution during development (“ontogeny recapitulates phylogeny”) and for coining several words we still use today, such as “ecology.” However, I personally enjoy him most for his extraordinary artistic skills. This book is a compilation of his illustrated prints of many different animals and enshrines his attention to detail and his odd sense of aesthetic perfection in nature.
— Rebecca Tarvin (TED-Ed lesson: Why don’t poisonous animals poison themselves?)

That’s What She Said: Wise Words from Influential Women by Kimothy Joy
There’s a new generation of female illustrators whose work combines art and insight in the same tradition as Kalman’s. My favorite is Kimothy Joy; her illustrated book That’s What She Said is a collection of colorful drawings and
razor-sharp quotes from some of history’s most inspiring female leaders, including Maya Angelou and Malala Yousafzai. I reach for this whenever I’m looking to feel re-energized in the fight for women’s issues.
— Alexandra Sacks (TED talk: A new way to think about the transition to motherhood)

My Favorite Things; Beloved Dog; and The Principles of Uncertainty — all by Maira Kalman (TED talk: The illustrated woman)
Illustrator Kalman tells stories through drawings and prose that are like the dreamscapes of the most delicious and magical children’s books — except they’re meant for adults. Keep My Favorite Things, Beloved Dog and Principles of Uncertainty on your nightstand or office shelf for whenever you’re craving a joyful escape to ponder everything from how memory works to how cake tastes.
— Alexandra Sacks (TED talk: A new way to think about the transition to motherhood)
If you’re craving a jolt of pure inspiration

Daring Greatly: How the Courage to Be Vulnerable Transforms the Way We Live, Love, Parent, and Lead by Brené Brown (TED talk: The power of vulnerability)
This book is all about having courage. Based on 12 years of research, it explains how vulnerability is both the core of difficult emotions like fear, grief and disappointment and the birthplace of love, belonging, joy, empathy, innovation and creativity. If we want to lead full lives, Brown encourages us to step into the arena in all aspects of our lives and dare greatly. She writes, “When we shut ourselves off from vulnerability, we distance ourselves from the experiences that bring purpose and meaning to our lives.”
— Christine Porath (TED talk: Why being respectful to your coworkers is good for business)

The Alchemist by Paulo Coelho
This is my favorite book. I reread it every year as a reminder that working through uncertainty, doubts and fears is perhaps the most important process on the path of following one’s dreams. Coelho’s beautiful fable is timeless, and the older I get, the more richly I relate to the various characters that influence Santiago, the curious main character who is pursuing his life’s purpose. I have recommended and gifted this book more times that I can recall. In fact, many years ago I was in a book club and my recommendation was met with spirited objection because as a fable, it was seen as not quite serious enough for our scholarly ladies. However, everyone quickly came to understand why I selected this gem.
— Nikki Clifton (TED talk: 3 ways business can fight sex trafficking)

This fictional story about the journey of a shepherd from Andalusia to Egypt has sold more than 30 million copies since it first appeared in 1988. It’s about taking risks to follow your dream — even when you’re tempted by safer or seemingly saner alternatives. It argues that fortune favours the brave – if you live boldly, things fall into place to ease your path.
— Alex Edmans (TED talk: What to trust in a “post-truth” world)

The Little Prince by Antoine de Saint-Exupéry
While ostensibly a children’s book, this gem has important lessons for adults. It’s about the importance of savoring the breadth, length, height and depth of life, rather than focusing on narrow goals. It encourages us to look at the world with childlike wonder rather than through the “rational” lens of a battle-weary grownup.
— Alex Edmans (TED talk: What to trust in a “post-truth” world)

Wishes Fulfilled: Mastering the Art of Manifesting by Wayne Dyer
This book changed my life. Dyer encourages readers to live at a higher level of awareness and consciousness, and he is unwavering in his instructions on how to master the art of manifesting. I have used positive affirmations, meditation and mindfulness to better understand myself and the law of attraction, and Wishes Fulfilled — along with his other popular books — have been instrumental in helping me grow and expand even further.
— Darieth Chisholm (TED talk: How revenge porn turns lives upside down
If you’d like reasons to feel hopeful about the future

How to Live Forever: The Enduring Power of Connecting the Generations by Marc Freedman
I think that Freedman is one of the wisest thought leaders in the aging and longevity world. With this book, he’s crafted a masterpiece — it’s written with such deep humanity and insight — in which he delivers a soulful rallying cry for intergenerational collaboration like we’ve never seen before. I finished it brimming with optimism about our future.
— Chip Conley (TED talk: What baby boomers can learn from millennials at work — and vice versa)

Adventures in the Anthropocene: A Journey to the Heart of the Planet We Made by Gaia Vince
It might seem strange to include a nonfiction book about climate change in a list of feel-good books, but in it, Vince tells how she quit her job as a journalist to travel the world and find people who are having to adapt to our changing world. What she uncovers is an uplifting story of the ingenuity of humans. It’s beautifully written, and you will come away inspired.
— Suzie Sheehy (TED talk: The case for curiosity-driven research)

The Rapture by Liz Jensen
Everyone is now aware of the warming planet, but when I read Jensen´s compelling thriller after it was published in 2009, it was the first time I had seen the warming planet portrayed almost as a character in itself. The heroine, Gabrielle, is a wheelchair-user — which adds to the odds stacked against her — in this story brimming with action and emotional conflict. In spite of the dark subject matter, I came away from it with renewed hope for humankind.
— Özlem Sara Cekic (TED talk: Why I have coffee with people who send me hate mail)

    readingreading listrecommended reading

FRESH IDEAS IN YOUR INBOX
TED Talk of the Day
Cara E. Yar Khan: The beautiful balance between courage and fear
Cara E. Yar Khan
The beautiful balance between courage and fear

    Similar Popular

    We humans
    A marriage researcher’s favorite books and podcasts for better relationships
    We humans
    When speaking a new language, what matters most is your attitude -- not your accuracy
    We humans
    Why are we so bad at predicting what will happen to us in the future?
    We humans
    A car-trip video playlist: 8 great TED-Ed lessons to make a drive fly by
    We humans
    Your 5-day gratitude challenge: 5 exercises to increase your gratefulness
    We humans
    When there's not enough family to celebrate Thanksgiving with
    We humans
    Your gift guide: Books for all kinds of readers, from TED
    We humans
    Gift guide: Biographies and memoirs

We humans
Reading list: 23 female TED speakers tell us about the books that shaped them
We humans
Your winter reading list: 56 books you won’t be able to put down
We humans
The two kinds of stories we tell about ourselves
Arts + Design
Restoring the world’s oldest library

    TED Talks Usage Policy
    Privacy Policy
    Advertising / Partnership
    TED.com Terms of Use
    Contact
    Jobs
    Press
    Help

© TED Conferences, LLC Powered by WordPress.com VIP
:)
</pre>
<pre ref ="sample2Ref" hidden>


    HomeMy Books
    Browse ▾
    Community ▾

    1

Most Popular Books Published In 1995
Top 200 books published in 1995 that people have added on Goodreads. (generated Dec 22, 2019 12:29PM)

1
	The Golden Compass (His Dark Materials, #1)
by Philip Pullman

3.97 avg rating — 1,187,833 ratings — published 1995 — added by 1,626,080 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
2
	Wicked: The Life and Times of the Wicked Witch of the West (The Wicked Years, #1)
by Gregory Maguire

3.53 avg rating — 555,617 ratings — published 1995 — added by 845,587 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
3
	A Child Called "It" (Dave Pelzer, #1)
by Dave Pelzer (Goodreads Author)

4.10 avg rating — 357,894 ratings — published 1995 — added by 547,112 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
4
	Dreams from My Father: A Story of Race and Inheritance
by Barack Obama

3.87 avg rating — 173,846 ratings — published 1995 — added by 417,982 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
5
	Kiss the Girls (Alex Cross, #2)
by James Patterson (Goodreads Author)

3.96 avg rating — 301,983 ratings — published 1995 — added by 406,813 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
6
	Assassin's Apprentice (Farseer Trilogy, #1)
by Robin Hobb (Goodreads Author)

4.15 avg rating — 210,810 ratings — published 1995 — added by 397,007 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
7
	Blindness
by José Saramago

4.11 avg rating — 173,732 ratings — published 1995 — added by 339,911 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
8
	Sabriel (Abhorsen, #1)
by Garth Nix (Goodreads Author)

4.17 avg rating — 170,161 ratings — published 1995 — added by 297,658 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
9
	Where the Heart Is
by Billie Letts

4.02 avg rating — 228,100 ratings — published 1995 — added by 290,263 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
10
	Naked in Death (In Death #1)
by J.D. Robb (Goodreads Author)

4.12 avg rating — 154,886 ratings — published 1995 — added by 265,902 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
11
	Left Behind (Left Behind, #1)
by Tim LaHaye

3.83 avg rating — 191,117 ratings — published 1995 — added by 260,899 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
12
	High Fidelity
by Nick Hornby

3.94 avg rating — 165,195 ratings — published 1995 — added by 248,152 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
13
	The Reader
by Bernhard Schlink

3.75 avg rating — 161,317 ratings — published 1995 — added by 245,110 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
14
	A Fine Balance
by Rohinton Mistry

4.36 avg rating — 118,953 ratings — published 1995 — added by 228,336 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
15
	The Rainmaker
by John Grisham (Goodreads Author)

3.93 avg rating — 157,294 ratings — published 1995 — added by 214,490 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
16
	Emotional Intelligence: Why It Can Matter More Than IQ
by Daniel Goleman (Goodreads Author)

4.01 avg rating — 70,965 ratings — published 1995 — added by 191,087 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
17
	Lies My Teacher Told Me: Everything Your American History Textbook Got Wrong
by James W. Loewen

3.97 avg rating — 49,569 ratings — published 1995 — added by 166,914 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
18
	The Lost World (Jurassic Park #2)
by Michael Crichton

3.77 avg rating — 112,424 ratings — published 1995 — added by 150,958 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
19
	The Demon-Haunted World: Science as a Candle in the Dark
by Carl Sagan

4.27 avg rating — 53,569 ratings — published 1995 — added by 145,030 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
20
	Rose Madder
by Stephen King (Goodreads Author)

3.70 avg rating — 89,888 ratings — published 1995 — added by 144,098 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
21
	Relic (Pendergast, #1)
by Douglas Preston (Goodreads Author)

4.02 avg rating — 87,780 ratings — published 1995 — added by 140,799 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
22
	The Millionaire Next Door: The Surprising Secrets of America's Wealthy
by Thomas J. Stanley

4.03 avg rating — 65,607 ratings — published 1995 — added by 140,747 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
23
	Notes from a Small Island
by Bill Bryson

3.92 avg rating — 86,899 ratings — published 1995 — added by 138,139 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
24
	The Diamond Age: Or, A Young Lady's Illustrated Primer
by Neal Stephenson (Goodreads Author)

4.19 avg rating — 76,880 ratings — published 1995 — added by 133,000 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
25
	Stone of Tears (Sword of Truth, #2)
by Terry Goodkind (Goodreads Author)

4.11 avg rating — 100,638 ratings — published 1995 — added by 132,942 people

Read
My rating:
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
[ 5 of 5 stars ]
26
	The Liars' Club
by Mary Karr

3.93 avg rating — 56,014 ratings — published 1995 — added by 132,126 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
27
	Absolute Power
by David Baldacci (Goodreads Author)

4.16 avg rating — 88,185 ratings — published 1995 — added by 131,065 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
28
	Practical Magic (Practical Magic #1)
by Alice Hoffman (Goodreads Author)

3.78 avg rating — 62,722 ratings — published 1995 — added by 128,044 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
29
	The Diary of Frida Kahlo: An Intimate Self-Portrait
by Frida Kahlo

3.86 avg rating — 35,404 ratings — published 1995 — added by 125,670 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
30
	Circus of the Damned (Anita Blake, Vampire Hunter, #3)
by Laurell K. Hamilton (Goodreads Author)

4.17 avg rating — 85,514 ratings — published 1995 — added by 114,181 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
31
	Watermelon (Walsh Family, #1)
by Marian Keyes

3.77 avg rating — 69,353 ratings — published 1995 — added by 114,094 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
32
	Longitude: The True Story of a Lone Genius Who Solved the Greatest Scientific Problem of His Time
by Dava Sobel

3.97 avg rating — 51,529 ratings — published 1995 — added by 111,243 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
33
	How the Irish Saved Civilization: The Untold Story of Ireland's Heroic Role from the Fall of Rome to the Rise of Medieval Europe
by Thomas Cahill

3.81 avg rating — 36,814 ratings — published 1995 — added by 110,983 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
34
	Memnoch the Devil (The Vampire Chronicles, #5)
by Anne Rice

3.75 avg rating — 72,856 ratings — published 1995 — added by 110,088 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
35
	Bloodsucking Fiends (A Love Story, #1)
by Christopher Moore (Goodreads Author)

3.94 avg rating — 57,224 ratings — published 1995 — added by 93,365 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
36
	Battlefield Of The Mind: Winning The Battle In Your Mind
by Joyce Meyer

4.34 avg rating — 52,767 ratings — published 1995 — added by 91,101 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
37
	Picture Perfect
by Jodi Picoult (Goodreads Author)

3.54 avg rating — 51,411 ratings — published 1995 — added by 89,932 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
38
	Hide and Seek
by James Patterson (Goodreads Author)

4.12 avg rating — 60,115 ratings — published 1995 — added by 87,578 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
39
	Belgarath the Sorcerer
by David Eddings

4.08 avg rating — 67,868 ratings — published 1995 — added by 86,439 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
40
	Lincoln
by David Herbert Donald

4.18 avg rating — 32,966 ratings — published 1995 — added by 86,152 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
41
	Mindhunter: Inside the FBI's Elite Serial Crime Unit
by John E. Douglas

4.07 avg rating — 28,492 ratings — published 1995 — added by 78,691 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
42
	The Last Coyote (Harry Bosch, #4; Harry Bosch Universe, #4)
by Michael Connelly (Goodreads Author)

4.23 avg rating — 55,248 ratings — published 1995 — added by 78,645 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
43
	The Watsons Go to Birmingham - 1963
by Christopher Paul Curtis

3.97 avg rating — 54,957 ratings — published 1995 — added by 78,264 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
44
	Glory in Death (In Death, #2)
by J.D. Robb (Goodreads Author)

4.26 avg rating — 47,847 ratings — published 1995 — added by 73,322 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
45
	Emperor Mage (Immortals, #3)
by Tamora Pierce (Goodreads Author)

4.30 avg rating — 53,710 ratings — published 1995 — added by 73,042 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
46
	Maskerade (Discworld, #18; Witches #5)
by Terry Pratchett

4.08 avg rating — 48,251 ratings — published 1995 — added by 72,892 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
47
	From Potter's Field (Kay Scarpetta, #6)
by Patricia Cornwell (Goodreads Author)

4.04 avg rating — 49,192 ratings — published 1995 — added by 72,083 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
48
	Black Hole
by Charles Burns

3.83 avg rating — 39,880 ratings — published 1995 — added by 71,475 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
49
	Deal Breaker (Myron Bolitar, #1)
by Harlan Coben (Goodreads Author)

3.95 avg rating — 41,771 ratings — published 1995 — added by 70,485 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
50
	The Horse Whisperer
by Nicholas Evans

3.80 avg rating — 48,753 ratings — published 1995 — added by 70,397 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
51
	The Winter King: A Novel of Arthur (The Warlord Chronicles, #1)
by Bernard Cornwell (Goodreads Author)

4.27 avg rating — 33,901 ratings — published 1995 — added by 66,538 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
52
	Czas pogardy (Saga o Wiedźminie, #2)
by Andrzej Sapkowski

4.27 avg rating — 42,479 ratings — published 1995 — added by 66,481 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
53
	The Calvin and Hobbes Tenth Anniversary Book
by Bill Watterson

4.63 avg rating — 49,689 ratings — published 1995 — added by 63,936 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
54
	World's End (The Sandman, #8)
by Neil Gaiman (Goodreads Author)

4.47 avg rating — 40,967 ratings — published 1995 — added by 63,227 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
55
	Beach Music
by Pat Conroy

4.15 avg rating — 41,575 ratings — published 1995 — added by 63,216 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
56
	Drown
by Junot Díaz

4.04 avg rating — 30,591 ratings — published 1995 — added by 61,977 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
57
	The Hundred Secret Senses
by Amy Tan (Goodreads Author)

3.99 avg rating — 38,881 ratings — published 1995 — added by 60,330 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
58
	Wonder Boys
by Michael Chabon

3.93 avg rating — 32,381 ratings — published 1995 — added by 54,956 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
59
	Conversations with God: An Uncommon Dialogue, Book 1
by Neale Donald Walsch

4.17 avg rating — 27,835 ratings — published 1995 — added by 54,090 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
60
	The Midwife's Apprentice
by Karen Cushman (Goodreads Author)

3.72 avg rating — 37,017 ratings — published 1995 — added by 53,927 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
61
	Behind the Scenes at the Museum
by Kate Atkinson

3.96 avg rating — 30,970 ratings — published 1995 — added by 51,140 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
62
	An Unquiet Mind: A Memoir of Moods and Madness
by Kay Redfield Jamison (Goodreads Author)

4.05 avg rating — 55,043 ratings — published 1995 — added by 51,029 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
63
	Born in Ice (Born In Trilogy, #2)
by Nora Roberts (Goodreads Author)

4.15 avg rating — 31,730 ratings — published 1995 — added by 50,221 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
64
	Simple Abundance: A Daybook of Comfort and Joy
by Sarah Ban Breathnach (Goodreads Author)

3.98 avg rating — 35,529 ratings — published 1995 — added by 48,355 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
65
	Born of Night (The League: Nemesis Rising #1)
by Sherrilyn Kenyon (Goodreads Author)

4.19 avg rating — 24,461 ratings — published 1995 — added by 47,679 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
66
	The Rapture of Canaan
by Sheri Reynolds (Goodreads Author)

3.82 avg rating — 32,899 ratings — published 1995 — added by 47,174 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
67
	Songs in Ordinary Time
by Mary McGarry Morris

3.70 avg rating — 30,506 ratings — published 1995 — added by 46,693 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
68
	Kissed by an Angel/The Power of Love/Soulmates (Kissed by an Angel, #1-3)
by Elizabeth Chandler

4.08 avg rating — 25,009 ratings — published 1995 — added by 45,849 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
69
	As Sure as the Dawn (Mark of the Lion, #3)
by Francine Rivers (Goodreads Author)

4.41 avg rating — 29,156 ratings — published 1995 — added by 44,413 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
70
	The Five Love Languages of Children
by Gary Chapman

4.20 avg rating — 16,624 ratings — published 1995 — added by 43,596 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
71
	An Anthropologist on Mars: Seven Paradoxical Tales
by Oliver Sacks

4.18 avg rating — 16,014 ratings — published 1995 — added by 43,176 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
72
	L is for Lawless (Kinsey Millhone, #12)
by Sue Grafton

3.92 avg rating — 27,434 ratings — published 1995 — added by 42,386 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
73
	The Scarlet Thread
by Francine Rivers (Goodreads Author)

4.18 avg rating — 26,294 ratings — published 1995 — added by 41,275 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
74
	The Tortilla Curtain
by T. Coraghessan Boyle (Goodreads Author)

3.65 avg rating — 26,393 ratings — published 1995 — added by 41,214 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
75
	Heaven, Texas (Chicago Stars, #2)
by Susan Elizabeth Phillips (Goodreads Author)

4.07 avg rating — 28,886 ratings — published 1995 — added by 41,037 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
76
	Lord of Scoundrels (Scoundrels, #3)
by Loretta Chase

4.11 avg rating — 26,118 ratings — published 1995 — added by 40,541 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
77
	The Wedding (Lairds' Fiancées, #2)
by Julie Garwood (Goodreads Author)

4.18 avg rating — 26,738 ratings — published 1995 — added by 39,653 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
78
	The Many Lives & Secret Sorrows of Josephine B. (Josephine Bonaparte, #1)
by Sandra Gulland (Goodreads Author)

4.10 avg rating — 15,280 ratings — published 1995 — added by 39,302 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
79
	The Oath
by Frank E. Peretti

4.07 avg rating — 25,278 ratings — published 1995 — added by 38,923 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
80
	The Prestige
by Christopher Priest

3.89 avg rating — 16,502 ratings — published 1995 — added by 37,350 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
81
	The Dark Elf Trilogy Collector's Edition (Forgotten Realms: Dark Elf Trilogy, #1-3; Legend of Drizzt, #1-3)
by R.A. Salvatore

4.34 avg rating — 24,900 ratings — published 1995 — added by 36,213 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
82
	The Lions of Al-Rassan
by Guy Gavriel Kay (Goodreads Author)

4.28 avg rating — 18,183 ratings — published 1995 — added by 36,006 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
83
	Darwin's Dangerous Idea: Evolution and the Meanings of Life
by Daniel C. Dennett

4.04 avg rating — 13,652 ratings — published 1995 — added by 35,542 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
84
	The Mermaids Singing (Tony Hill & Carol Jordan, #1)
by Val McDermid

3.97 avg rating — 17,080 ratings — published 1995 — added by 35,373 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
85
	Don't Die, My Love
by Lurlene McDaniel (Goodreads Author)

4.14 avg rating — 15,588 ratings — published 1995 — added by 34,608 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
86
	Running Out of Time
by Margaret Peterson Haddix

3.99 avg rating — 22,499 ratings — published 1995 — added by 34,135 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
87
	Microserfs
by Douglas Coupland (Goodreads Author)

3.88 avg rating — 22,659 ratings — published 1995 — added by 34,130 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
88
	Rise of a Merchant Prince (The Serpentwar Saga, #2)
by Raymond E. Feist

4.05 avg rating — 25,289 ratings — published 1995 — added by 33,824 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
89
	A Place Called Freedom
by Ken Follett (Goodreads Author)

3.94 avg rating — 20,556 ratings — published 1995 — added by 33,673 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
90
	The New Best Recipe
by Cook's Illustrated Magazine

4.18 avg rating — 19,133 ratings — published 1995 — added by 33,430 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
91
	After the Night
by Linda Howard

4.09 avg rating — 21,495 ratings — published 1995 — added by 32,910 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
92
	Officer Buckle and Gloria
by Peggy Rathmann

4.17 avg rating — 27,852 ratings — published 1995 — added by 32,528 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
93
	The Jesus I Never Knew
by Philip Yancey (Goodreads Author)

4.19 avg rating — 17,945 ratings — published 1995 — added by 31,959 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
94
	Thinking in Pictures: My Life with Autism
by Temple Grandin

4.12 avg rating — 12,672 ratings — published 1995 — added by 31,061 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
95
	A Light in the Window (Mitford Years, #2)
by Jan Karon

4.24 avg rating — 21,571 ratings — published 1995 — added by 31,051 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
96
	Bloodchild and Other Stories
by Octavia E. Butler

4.32 avg rating — 11,623 ratings — published 1995 — added by 30,958 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
97
	Let Me Call You Sweetheart
by Mary Higgins Clark (Goodreads Author)

3.86 avg rating — 20,136 ratings — published 1995 — added by 30,491 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
98
	A Monstrous Regiment of Women (Mary Russell and Sherlock Holmes, #2)
by Laurie R. King (Goodreads Author)

4.04 avg rating — 21,033 ratings — published 1995 — added by 30,430 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
99
	Strange Highways
by Dean Koontz (Goodreads Author)

3.85 avg rating — 18,296 ratings — published 1995 — added by 30,297 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
100
	The Witness
by Sandra Brown (Goodreads Author)

really liked it 4.00 avg rating — 16,980 ratings — published 1995 — added by 29,650 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
101
	The Persian Pickle Club
by Sandra Dallas

3.79 avg rating — 16,537 ratings — published 1995 — added by 29,501 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
102
	Nourishing Traditions: The Cookbook That Challenges Politically Correct Nutrition and the Diet Dictocrats
by Sally Fallon

4.17 avg rating — 12,037 ratings — published 1995 — added by 29,195 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
103
	Outcast of Redwall (Redwall, #8)
by Brian Jacques

3.92 avg rating — 18,520 ratings — published 1995 — added by 28,913 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
104
	Sidetracked (Kurt Wallander, #5)
by Henning Mankell

4.07 avg rating — 18,406 ratings — published 1995 — added by 28,741 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
105
	American Tabloid (Underworld USA #1)
by James Ellroy

4.21 avg rating — 13,531 ratings — published 1995 — added by 28,661 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
106
	Wayside School Gets A Little Stranger (Wayside School, #3)
by Louis Sachar

4.19 avg rating — 19,107 ratings — published 1995 — added by 27,005 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
107
	Mind Prey (Lucas Davenport, #7)
by John Sandford

4.21 avg rating — 17,400 ratings — published 1995 — added by 26,974 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
108
	Coming Home
by Rosamunde Pilcher

4.29 avg rating — 16,141 ratings — published 1995 — added by 26,949 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
109
	The Julius House (Aurora Teagarden, #4)
by Charlaine Harris (Goodreads Author)

3.84 avg rating — 15,615 ratings — published 1995 — added by 26,851 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
110
	The Secret Art of Dr. Seuss
by Dr. Seuss

4.04 avg rating — 10,328 ratings — published 1995 — added by 26,764 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
111
	A Killing Frost (Tomorrow, #3)
by John Marsden

4.20 avg rating — 16,821 ratings — published 1995 — added by 26,226 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
112
	The Rings of Saturn
by W.G. Sebald

4.26 avg rating — 9,274 ratings — published 1995 — added by 25,997 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
113
	The Unconsoled
by Kazuo Ishiguro

3.53 avg rating — 9,446 ratings — published 1995 — added by 25,754 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
114
	Interesting Times: The Play
by Stephen Briggs (Adaptor)

4.14 avg rating — 20,733 ratings — published 1995 — added by 25,523 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
115
	Sleepers
by Lorenzo Carcaterra

4.21 avg rating — 12,418 ratings — published 1995 — added by 25,327 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
116
	Morning, Noon & Night
by Sidney Sheldon

3.65 avg rating — 15,901 ratings — published 1995 — added by 25,321 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
117
	The Ghost Road (Regeneration, #3)
by Pat Barker

4.11 avg rating — 14,662 ratings — published 1995 — added by 25,134 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
118
	Slowness
by Milan Kundera

3.66 avg rating — 13,685 ratings — published 1995 — added by 24,948 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
119
	The Seventh Scroll (Ancient Egypt, #2)
by Wilbur Smith

4.12 avg rating — 15,883 ratings — published 1995 — added by 24,939 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
120
	The Wayfarer Redemption (Wayfarer Redemption, #1)
by Sara Douglass

3.94 avg rating — 15,696 ratings — published 1995 — added by 24,924 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
121
	The Watcher in the Shadows (Niebla, #3)
by Carlos Ruiz Zafón

3.77 avg rating — 13,034 ratings — published 1995 — added by 24,601 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
122
	Independence Day
by Richard Ford

3.86 avg rating — 14,364 ratings — published 1995 — added by 24,582 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
123
	Gods and Kings (Chronicles of the Kings, #1)
by Lynn Austin (Goodreads Author)

4.32 avg rating — 10,932 ratings — published 1995 — added by 24,564 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
124
	Fingerprints of the Gods: The Evidence of Earth's Lost Civilization
by Graham Hancock (Goodreads Author)

4.18 avg rating — 8,118 ratings — published 1995 — added by 24,455 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
125
	Night of the Ninjas (Magic Tree House, #5)
by Mary Pope Osborne

3.95 avg rating — 14,541 ratings — published 1995 — added by 24,291 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
126
	The Moor's Last Sigh
by Salman Rushdie

3.92 avg rating — 11,950 ratings — published 1995 — added by 23,904 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
127
	Rena's Promise: A Story of Sisters in Auschwitz
by Rena Kornreich Gelissen

4.31 avg rating — 8,213 ratings — published 1995 — added by 23,746 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
128
	Splendid (The Splendid Trilogy, #1)
by Julia Quinn (Goodreads Author)

3.91 avg rating — 14,978 ratings — published 1995 — added by 23,693 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
129
	Double Act
by Jacqueline Wilson

3.72 avg rating — 15,337 ratings — published 1995 — added by 23,606 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
130
	Buffett: The Making of an American Capitalist
by Roger Lowenstein

4.27 avg rating — 10,304 ratings — published 1995 — added by 23,231 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
131
	Ladder of Years
by Anne Tyler

3.72 avg rating — 14,316 ratings — published 1995 — added by 22,455 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
132
	Reservation Blues
by Sherman Alexie

3.98 avg rating — 12,231 ratings — published 1995 — added by 21,930 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
133
	A Civil Action
by Jonathan Harr

3.97 avg rating — 14,001 ratings — published 1995 — added by 21,924 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
134
	Mysterious Skin
by Scott Heim

4.03 avg rating — 8,671 ratings — published 1995 — added by 21,789 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
135
	The Wars of the Roses
by Alison Weir

3.96 avg rating — 7,160 ratings — published 1995 — added by 21,560 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
136
	Afternoon on the Amazon (Magic Tree House, #6)
by Mary Pope Osborne

3.93 avg rating — 12,948 ratings — published 1995 — added by 21,256 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
137
	On Killing: The Psychological Cost of Learning to Kill in War and Society
by Dave Grossman

4.17 avg rating — 7,292 ratings — published 1995 — added by 21,231 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
138
	Alvin Journeyman (Tales of Alvin Maker, #4)
by Orson Scott Card

3.73 avg rating — 14,951 ratings — published 1995 — added by 21,210 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
139
	Wit
by Margaret Edson

4.21 avg rating — 12,591 ratings — published 1995 — added by 21,135 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
140
	Warlock (Ancient Egypt, #3)
by Wilbur Smith

4.04 avg rating — 13,028 ratings — published 1995 — added by 20,959 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
141
	The Return of Rafe MacKade (The MacKade Brothers, #1)
by Nora Roberts (Goodreads Author)

4.10 avg rating — 11,821 ratings — published 1995 — added by 20,951 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
142
	Dragons of Summer Flame (Dragonlance: The Second Generation, #2)
by Margaret Weis (Goodreads Author)

3.86 avg rating — 14,445 ratings — published 1995 — added by 20,847 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
143
	Stormy Weather
by Carl Hiaasen

3.95 avg rating — 14,242 ratings — published 1995 — added by 20,640 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
144
	Under the Black Flag: The Romance and the Reality of Life Among the Pirates
by David Cordingly

3.68 avg rating — 7,302 ratings — published 1995 — added by 20,164 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
145
	For the Roses (Rose, #1)
by Julie Garwood (Goodreads Author)

4.04 avg rating — 12,887 ratings — published 1995 — added by 20,048 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
146
	Flag in Exile (Honor Harrington, #5)
by David Weber

4.23 avg rating — 15,333 ratings — published 1995 — added by 19,930 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
147
	Cetaganda (Vorkosigan Saga, #9)
by Lois McMaster Bujold (Goodreads Author)

4.17 avg rating — 15,261 ratings — published 1995 — added by 19,911 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
148
	Snow, Glass, Apples
by Neil Gaiman (Goodreads Author)

4.19 avg rating — 6,979 ratings — published 1995 — added by 19,585 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
149
	Sabbath's Theater
by Philip Roth

3.85 avg rating — 8,270 ratings — published 1995 — added by 19,552 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
150
	الحب في المنفى
by Bahaa Taher

3.83 avg rating — 5,892 ratings — published 1995 — added by 19,420 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
151
	True Betrayals
by Nora Roberts (Goodreads Author)

3.98 avg rating — 11,245 ratings — published 1995 — added by 19,295 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
152
	Night Sins (Deer Lake, #1)
by Tami Hoag (Goodreads Author)

3.96 avg rating — 10,376 ratings — published 1995 — added by 19,281 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
153
	Shepherding a Child's Heart
by Tedd Tripp

4.22 avg rating — 9,818 ratings — published 1995 — added by 19,176 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
154
	Enigma
by Robert Harris (Goodreads Author)

3.86 avg rating — 11,818 ratings — published 1995 — added by 18,983 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
155
	The Missionary Position: Mother Teresa in Theory and Practice
by Christopher Hitchens

4.06 avg rating — 8,407 ratings — published 1995 — added by 18,879 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
156
	Op-Center (Tom Clancy's Op-Center, #1)
by Jeff Rovin (Goodreads Author)

3.57 avg rating — 11,449 ratings — published 1995 — added by 18,755 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
157
	Raptor Red
by Robert T. Bakker

3.92 avg rating — 7,781 ratings — published 1995 — added by 18,633 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
158
	On Gold Mountain: The One-Hundred-Year Odyssey of My Chinese-American Family
by Lisa See (Goodreads Author)

3.93 avg rating — 8,671 ratings — published 1995 — added by 18,501 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
159
	Dead Man's Walk (Lonesome Dove, #3)
by Larry McMurtry

3.93 avg rating — 10,937 ratings — published 1995 — added by 18,461 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
160
	My Story: "A Child Called It", "The Lost Boy", "A Man Named Dave"
by Dave Pelzer (Goodreads Author)

4.20 avg rating — 10,121 ratings — published 1995 — added by 18,051 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
161
	Running Scared
by Lisa Jackson (Goodreads Author)

3.93 avg rating — 4,284 ratings — published 1995 — added by 18,017 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
162
	Crash
by Jerry Spinelli

3.78 avg rating — 11,382 ratings — published 1995 — added by 17,844 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
163
	High Tide in Tucson
by Barbara Kingsolver

4.04 avg rating — 10,422 ratings — published 1995 — added by 17,493 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
164
	The Stories of Vladimir Nabokov
by Vladimir Nabokov

4.30 avg rating — 6,499 ratings — published 1995 — added by 17,461 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
165
	Media Control: The Spectacular Achievements of Propaganda
by Noam Chomsky

4.02 avg rating — 5,516 ratings — published 1995 — added by 17,403 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
166
	Intuitive Eating: A Revolutionary Program That Works
by Evelyn Tribole

4.24 avg rating — 6,324 ratings — published 1995 — added by 17,374 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
167
	Zombie
by Joyce Carol Oates

3.34 avg rating — 7,616 ratings — published 1995 — added by 17,303 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
168
	The MacKade Brothers: Rafe and Jared (MacKades #1-2)
by Nora Roberts (Goodreads Author)

4.16 avg rating — 10,801 ratings — published 1995 — added by 17,149 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
169
	Black Cross
by Greg Iles (Goodreads Author)

4.18 avg rating — 9,856 ratings — published 1995 — added by 17,103 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
170
	Dancing at Midnight (The Splendid Trilogy, #2)
by Julia Quinn (Goodreads Author)

3.79 avg rating — 10,749 ratings — published 1995 — added by 16,679 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
171
	Voodoo River (Elvis Cole, #5)
by Robert Crais

4.15 avg rating — 11,448 ratings — published 1995 — added by 16,591 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
172
	The Fire Rose (Elemental Masters, #0)
by Mercedes Lackey

3.96 avg rating — 9,632 ratings — published 1995 — added by 16,476 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
173
	Crown of Shadows (The Coldfire Trilogy, #3)
by C.S. Friedman

4.17 avg rating — 11,770 ratings — published 1995 — added by 16,202 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
174
	Braveheart
by Randall Wallace (Goodreads Author)

4.21 avg rating — 12,387 ratings — published 1995 — added by 16,169 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
175
	Taking Charge of Your Fertility: The Definitive Guide to Natural Birth Control, Pregnancy Achievement, and Reproductive Health
by Toni Weschler (Goodreads Author)

4.52 avg rating — 8,138 ratings — published 1995 — added by 16,049 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
176
	Junie B. Jones and the Yucky Blucky Fruitcake (Junie B. Jones, #5)
by Barbara Park

4.01 avg rating — 10,015 ratings — published 1995 — added by 15,983 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
177
	Marabou Stork Nightmares
by Irvine Welsh

3.86 avg rating — 9,560 ratings — published 1995 — added by 15,901 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
178
	Storm Rising (Valdemar: Mage Storms, #2)
by Mercedes Lackey

4.02 avg rating — 11,362 ratings — published 1995 — added by 15,899 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
179
	The White Gryphon (Valdemar: Mage Wars, #2)
by Mercedes Lackey

3.91 avg rating — 11,046 ratings — published 1995 — added by 15,816 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
180
	Red River, Vol. 1 (Red River, #1)
by Chie Shinohara

4.23 avg rating — 10,338 ratings — published 1995 — added by 15,781 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
181
	Witches' Brew (Magic Kingdom of Landover, #5)
by Terry Brooks (Goodreads Author)

3.90 avg rating — 9,998 ratings — published 1995 — added by 15,769 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
182
	The Romanovs: The Final Chapter
by Robert K. Massie

4.04 avg rating — 6,131 ratings — published 1995 — added by 15,695 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
183
	The Pride of Jared MacKade (The MacKade Brothers, #2)
by Nora Roberts (Goodreads Author)

4.09 avg rating — 9,307 ratings — published 1995 — added by 15,653 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
184
	The Splendour Falls
by Susanna Kearsley (Goodreads Author)

3.72 avg rating — 9,185 ratings — published 1995 — added by 15,650 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
185
	Why Do Men Have Nipples?: Hundreds of Questions You'd Only Ask a Doctor After Your Third Martini
by Mark Leyner

3.41 avg rating — 8,680 ratings — published 1995 — added by 15,582 people

Want to Read
Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
186
	Sophie's Heart
by Lori Wick

4.24 avg rating — 9,752 ratings — published 1995 — added by 15,572 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
187
	The Story of Ruby Bridges
by Robert Coles

4.43 avg rating — 11,573 ratings — published 1995 — added by 15,554 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
188
	The Origin of Satan: How Christians Demonized Jews, Pagans and Heretics
by Elaine Pagels

3.90 avg rating — 5,867 ratings — published 1995 — added by 15,467 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
189
	The Very Lonely Firefly
by Eric Carle

4.16 avg rating — 9,567 ratings — published 1995 — added by 15,259 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
190
	Let It Bleed (Inspector Rebus, #7)
by Ian Rankin (Goodreads Author)

4.04 avg rating — 10,466 ratings — published 1995 — added by 15,195 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
191
	Charlie All Night
by Jennifer Crusie (Goodreads Author)

3.64 avg rating — 10,275 ratings — published 1995 — added by 15,135 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
192
	Touching from a Distance: Ian Curtis and Joy Division
by Deborah Curtis

3.90 avg rating — 6,662 ratings — published 1995 — added by 14,988 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
193
	Freedom's Landing (Catteni, #1)
by Anne McCaffrey

3.94 avg rating — 9,767 ratings — published 1995 — added by 14,876 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
194
	The Christmas Miracle of Jonathan Toomey
by Susan Wojciechowski

4.43 avg rating — 10,589 ratings — published 1995 — added by 14,870 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
195
	Lovingkindness: The Revolutionary Art of Happiness
by Sharon Salzberg (Goodreads Author)

4.24 avg rating — 5,050 ratings — published 1995 — added by 14,849 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
196
	All That Glitters (Landry, #3)
by V.C. Andrews

3.89 avg rating — 8,695 ratings — published 1995 — added by 14,732 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
197
	Patty Jane's House of Curl
by Lorna Landvik (Goodreads Author)

3.86 avg rating — 9,524 ratings — published 1995 — added by 14,519 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
198
	The Potato Factory (The Potato Factory, #1)
by Bryce Courtenay

4.11 avg rating — 8,648 ratings — published 1995 — added by 14,440 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
199
	My Point... And I Do Have One
by Ellen DeGeneres

3.67 avg rating — 7,463 ratings — published 1995 — added by 14,291 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
200
	Five Days in Paris
by Danielle Steel

3.57 avg rating — 7,638 ratings — published 1995 — added by 14,209 people

Rate this book
1 of 5 stars
2 of 5 stars
3 of 5 stars
4 of 5 stars
5 of 5 stars
By Year
By Month
« Prev
Next »

Browse Books
New Releases
Discussion
Listopia
Most read
Popular books by date
Popular bookclub books
Popular shelves
Recent reviews



Don't agree?
Vote on the best books of 1995 »
Company

    About us
    Careers
    Terms
    Privacy
    Help

Work with us

    Authors
    Advertise
    Authors & ads blog
    API

Connect

    © 2019 Goodreads, Inc.
    Mobile version

</pre>
<pre ref = "sample3Ref" hidden>
Bauer, Yehuda (1994). Jews for Sale? Nazi-Jewish Negotiations 1933-1945. Yale University Press. ISBN 0-300-06852-2.
Berenbaum, Michael (1990). A Mosaic of Victims: Non-Jews Persecuted and Murdered by the Nazis.
Bergen, Doris (2009). War and Genocide: Concise History of the Holocaust.
Black, Edwin (2010). The Farhud: The Arab-Nazi Alliance in the Holocaust. Dialog Press. ISBN 0-914153-14-5.
Braham, Randolph (1994) [1981]. The Politics of Genocide: The Holocaust in Hungary. Columbia University Press. ISBN 0-88033-247-6.
Braham, Randolph (2011). The Auschwitz Reports and the Holocaust in Hungary. Columbia University Press.
Chalmers, Beverley (2015). Birth, Sex and Abuse: Women's Voices Under Nazi Rule. Grosvenor House Publishing Ltd. ISBN 1781483531.
Davies, Norman; Lukas, Richard C. (2001) [1996]. Forgotten Holocaust: The Poles Under German Occupation.
Dean, Martin (2008). Robbing the Jews: The Confiscation of Jewish Property in the Holocaust. Cambridge University Press.
Evans, Suzanne (2004). Forgotten Crimes: The Holocaust and People with Disabilities.
Friedländer, Saul (1998). The Years of Persecution: Nazi Germany and the Jews, 1933-1939. Vol. 1.
Grau, Gunter; Shoppmann, Claudia (1995). The Hidden Holocaust?: Gay and Lesbian Persecution in Germany 1933-45.
Hedgepeth, Sonja; Saidel, Rochelle (2010). Sexual Violence against Jewish Women during the Holocaust.
Peukert, Detlev (1994). "The Genesis of the 'Final Solution' from the Spirit of Science". In Thomas Childers; Jane Caplan (eds.). Reevaluating the Third Reich. New York: Holmes & Meier. pp. 234–252. ISBN 0-8419-1178-9.
Rees, Laurence (2017). The Holocaust: A New History. London: Viking Press. ISBN 978-1610398442.
Améry, Jean (1980). At the Mind's Limits: Contemplations by a Survivor on Auschwitz and its Realities.
Blitz Konig, Nanette (2018). Holocaust Memoirs of a Bergen-Belsen Survivor and Classmate of Anne Frank. Amsterdam Publishers. ISBN 9789492371614.
Dittman, Anita (2005). Trapped in Hitler's Hell. ISBN 0-9721512-8-1.
Gerrard, Mady. Full Circle. KLPM. ISBN 978-0955865008.
Kogon, Eugen (1974). Der SS-Staat. Das System der deutschen Konzentrationslager (in German).
Rittner, Carol; Roth, John K. (1998). Different Voices: Women and the Holocaust.
Stojka, Ceija (1988). We Live in Seclusion: The Memories of a Romni.
Steinberg, Manny (2014). Outcry: Holocaust Memoirs. Amsterdam Publishers. ISBN 978-9-082103137.
Wetzler, Alfréd (2007). Escape from Hell: The True Story of the Auschwitz Protocol. Berghahn Books.
Winter, Walter (2004). Winter Time: Memoirs of a German Sinto who Survived Auschwitz.
Czech, Danuta (1999). Auschwitz Chronicle: 1939-1945.
Dean, Martin (1999). Collaboration in the Holocaust: Crimes of the Local Police in Belorussia and Ukraine.
Fings, Karola; Kenrick, Donald, eds. (1999). The Gypsies During the Second World War.
Hogan, David J.; Aretha, David, eds. (2000). The Holocaust Chronicle: A History in Words and Pictures. Lincolnwood, IL: Publications International.
Pressac, Jean-Claude (1989). Auschwitz: Technique and operation of the gas chambers.
Agamben, Giorgio (1999). Remnants of Auschwitz: The Witness and the Archive.
Bloxham, Donald (2009). The Final Solution: A Genocide.
Lawson, Tom (2010). Debates on the Holocaust. University of Manchester Press.
Leff, Laurel (2005). Buried By The Times: The Holocaust And America's Most Important Newspaper. Cambridge University Press. ISBN 0-521-81287-9.
Mason, Timothy. "Intention and Explanation: A Current Controversy about the Interpretation of National Socialism". In Marrus, Michael R. (ed.). The Nazi Holocaust Part 3, The "Final Solution": The Implementation of Mass Murder. Vol. 1. Westpoint, CT: Mecler. pp. 3–20.
Niewyk, Donald L. (1992). Holocaust: Problems & Perspective of Interpretation.
</pre>
</div>
</template>


<style lang="less">
pre{
    display:hidden;
    font-family: inherits;
}</style>


