#part01.dat
#part02.dat
#part03.dat
#part04.dat
#part05.dat
#part06.dat
#part07.dat
#part08.dat
#part09.dat
#part10.dat
#part11.dat
#part12.dat
#part13.dat
#part14.dat
#part15.dat
#part16.dat
#part17.dat
#part18.dat
#part19.dat
#part20.dat
#part21.dat
#part22.dat
#part23.dat
#part24.dat
#part25.dat
#part26.dat
#part27.dat
#part28.dat
#part29.dat

for part in "29" "02" "28" "03" "27" "04" "26" "05" "25" "06" "24" "07" "23" "08" "22"; do
	type="marc"
	source="lc/part${part}.dat"
	progress="progress/$part"
	./import.sh $type $source >$progress 2>&1 || exit 1
done

