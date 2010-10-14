#!/usr/bin/env python

import datetime, csv, os, sys, collections, subprocess, tempfile

from optparse import OptionParser

def main():
    """
    Uses gnuplot to graph a csv produced by crunch_logs.py
    """
    parser = OptionParser(usage="%prog file")
    parser.add_option("-l", "--limit", dest="limit", type="int",
                      default=10,
                      help="The maximum number of lines to emit")
    parser.add_option("-t", "--title", dest="title",
                      default=None,
                      help="The title for the plot")

    options, args = parser.parse_args()

    if len(args) != 1:
        parser.error("file required")

    in_fn = os.path.abspath(args[0])

    input = csv.reader(open(in_fn), delimiter='\t')
    data = collections.defaultdict(dict)
    dates = set()

    totals = {}

    for date, value, count in input:
        if date == "totals":
            totals[value] = count
        else:
            dates.add(date)
            data[value][date] = count

    values = sorted(totals.keys(), key=lambda k: int(totals[k]), reverse=True)[:options.limit]
    data = dict((k, v) for k, v in data.iteritems() if k in values)

    dates = sorted(dates)
    
    dat_f = tempfile.NamedTemporaryFile(prefix="%s.dat" % os.path.splitext(os.path.basename(in_fn))[0], 
                                        delete=False)
    plt_f = tempfile.NamedTemporaryFile(prefix="%s.plt" % os.path.splitext(os.path.basename(in_fn))[0], 
                                        delete=False)

    print "writing to %s, %s" % (plt_f.name, dat_f.name)
    output_fn = os.path.join(os.path.dirname(in_fn), "%s.png" % os.path.splitext(in_fn)[0])
    for line in (#"set terminal x11",
        'set terminal png medium size 1500,1500',
        "set xlabel 'date'",
        'set ylabel "num_requests"',
        "set xdata time",
        'set timefmt "%Y-%m-%d"',
        'set format x "%b %d"',
        'set format y "%-.0f"',
        'set output "%s"\n' % output_fn
    ):
        plt_f.write("%s\n" % line)

    if options.title:
        plt_f.write('set title "%s"\n' % options.title)

    plot_cmd = []
    for i, v in enumerate(values):
        plot_cmd.append('"%s" using 1:%d title "%s" with lines' % (dat_f.name, i + 2, v))
    
    plt_f.write("plot %s\n;" % ", \\\n\t".join(plot_cmd))

    dat_f.write("%s\n" % "\t".join(["#", "date"] + values))

    for date in dates:
        dat_f.write("\t%s\n" % "\t".join([date] + [str(data[v].get(date, 0)) for v in values]))

    #plt_f.write("pause -1\n")

    plt_f.close()
    dat_f.close()

    print "running %s" % " ".join(["gnuplot", plt_f.name])
    assert subprocess.call(["gnuplot", plt_f.name]) == 0
    print "plot written to %s" % output_fn

if __name__ == "__main__":
    main()
