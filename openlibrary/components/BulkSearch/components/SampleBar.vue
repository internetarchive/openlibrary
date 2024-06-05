<template>
	<div>
		<label>Sample Data:
			<select v-model="selectedValue">
				<option>Choose sample...</option>
				<option value="sample1">TED’s 2018 winter reading list</option>
				<option value="sample2">2023 Public Domain Day</option>
				<option value="sample3">Holocaust Wikipedia citations</option>
			</select>
		</label>
<pre ref="sample1Ref" hidden>
	Djamaluddin Adinegoro - Darah Muda (Young Blood)
	Ion Agârbiceanu - Legea minții
    Anthony Berkeley - Cicely Disappears
    Arthur Bernède - Belphégor
   Tjoe Hong Bok - Setangan Berloemoer Darah (A Glove Covered in Blood)
    James Boyd - Marching On
    Lynn Brock - The Kink
    Edgar Rice Burroughs - The Outlaw of Torn
    James Branch Cabell - Something About Eve
    Willa Cather - Death Comes for the Archbishop
    Blaise Cendrars - La Confession de Dan Yack
    Agatha Christie - The Big Four
    J.J. Connington        Murder in the Maze        Tragedy at Ravensthorpe
	Jaime de Angulo - The Lariat
    Mazo de la Roche - Jalna
    Warwick Deeping - Kitty
</pre>
		<pre ref="sample2Ref" hidden>
		Virginia Woolf, To the Lighthouse
		Arthur Conan Doyle, The Case-Book of Sherlock Holmes
		Willa Cather, Death Comes for the Archbishop
		Countee Cullen, Copper Sun
		A. A. Milne, Now We Are Six, illustrations by E. H. Shepard
		Thornton Wilder, The Bridge of San Luis Rey
       Ernest Hemingway, Men Without Women (collection of short stories)
       William Faulkner, Mosquitoes
        Agatha Christie, The Big Four
       Edith Wharton, Twilight Sleep
        Herbert Asbury, The Gangs of New York (the original 1927 publication)
        Franklin W. Dixon (pseudonym), The Tower Treasure (the first Hardy Boys book)
        Hermann Hesse, Der Steppenwolf (in the original German)
        Franz Kafka, Amerika (in the original German)
        Marcel Proust, Le Temps retrouvé Vol. 1 & Vol. 2  (the final installment of In Search of Lost Time, in the original French)
</pre>
		<pre ref="sample3Ref" hidden>
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
        usedSample(newValue) {
            this.$emit('sample', newValue)
        }
    },
    computed: {
        usedSample() {
            const dict = { sample1: this.sample1, sample2: this.sample2, sample3: this.sample3 }
            return dict[this.selectedValue]
        }
    }
}
</script>

<style lang="less">
pre {
	display: hidden;
	font-family: inherits;
}
</style>
