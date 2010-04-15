#!/usr/bin/env ruby

require 'rubygems'
require 'json'

isbn_map = {}
IO.popen("/usr/bin/env gunzip --stdout goodreads_isbns.csv.gz", "r") do |f|
  until f.eof?
    line = f.gets.strip
    next unless line =~ /^\d+,/
    goodreads_id, isbn_10, isbn_13 = line.split(",")
    [isbn_10, isbn_13].each do |isbn|
      next if isbn.to_s.strip.empty?
      if isbn_map.has_key?(isbn)
        $stderr.puts "WARN: Duplicate ISBN #{isbn}, for Goodreads ID #{goodreads_id}!"
        next
      end

      isbn_map[isbn] = goodreads_id
      $stderr.puts "Read #{isbn_map.length} ISBN map entries" if (isbn_map.length % 250_000).zero?
    end
  end
end

$stdout.puts ["OpenlibraryId", "Isbn", "GoodreadsId"].join("\t")
IO.popen("/usr/bin/env gunzip --stdout edition-2009-09-11.txt.gz") do |f|
  until f.eof?
    line = f.gets.strip
    olid, ed_type, json = line.split("\t")
    ed = JSON.parse(json)

    isbns = []
    isbns += ed["isbn"] unless ed["isbn"].nil?
    isbns += ed["isbn_10"] unless ed["isbn_10"].nil?
    isbns += ed["isbn_13"] unless ed["isbn_13"].nil?
    next if isbns.empty?

    isbns.each do |isbn|
      next unless isbn_map.has_key?(isbn)
      $stdout.puts [olid, isbn, isbn_map[isbn]].join("\t")
    end
  end
end

