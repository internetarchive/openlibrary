
source_id=${1:-"LC"}
file_loc=${2:-"marc_records_scriblio_net/part01.dat"}
file_url="http://www.archive.org/download/${file_loc}"
# unfortunately we need a seekable file to parse, so can't just pipe this from the archive
#file=${3:-"/0/ttk/marc_records_scriblio_net/part01.dat"}
file=${3:-"$HOME/pharos/data/parts/part01.dat"}

export PHAROS_REPO="../.."
export PYTHONPATH="$PHAROS_REPO"

echo "parsing records from source '$source_id', file '$file_loc'"
exec python2.5 parse.py $source_id $file_loc < $file

