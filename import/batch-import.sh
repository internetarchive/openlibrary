for part in "09" "12"; do
	type="marc"
	source="lc/part${part}.dat"
	progress="progress/$part"
	./import.sh $type $source >>$progress 2>&1 || exit 1
done
