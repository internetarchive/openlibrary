#!/usr/bin/perl

use strict;
use warnings;
use lib '/home/edward/lib/perl5';
use JSON::XS;
use Parse::MediaWikiDump;

#my $coder = JSON::XS->new->ascii;
my $coder = JSON::XS->new->utf8;

#binmode STDOUT, ":utf8";

open my $fh, "-|", "curl http://download.wikimedia.org/enwiki/20081008/enwiki-20081008-pages-articles.xml.bz2 | bzip2 -dc -" or die $!;
my $pages = Parse::MediaWikiDump::Pages->new($fh);

sub get_template {
    my ($template, $text) = @_;
    $text =~ /({{\s*$template)/igc or return;
    my $depth = 1;
    my $infobox = $1;
    while ($depth) {
        unless ($text =~ /\G(.*?({{|}}))/sgc) {
            return;
        }
        $infobox .= $1;
        $2 eq '}}' and do { $depth--; next };
        $2 eq '{{' and do { $depth++; next };
    }
    return $infobox;
}

my $page;
open my $redirect, ">", 'redirects' or die;
open my $people, ">", 'people' or die;
while(defined($page = $pages->next)) {
    $page->namespace and next;
    if ($page->redirect) {
        print $redirect $coder->encode([$page->title, $page->redirect]), "\n";
        next;
    }
    my $cats = $page->categories;
    $cats or next;
    my $text = ${$page->text};
    my $len = length($text);
    my $skip = 1;
    for (@$cats) {
        /(writer|people|birth|death)/ or next;
        $skip = 0;
        last;
    }
    $skip and next;
    my %out = (
        title => $page->title,
        cats => $cats,
        len => $len,
    );
    for (qw(persondata defaultsort infobox lifetime)) {
        my $template = get_template($_, $text);
        $template and $out{$_} = $template;
    }
    print $people $coder->encode(\%out), "\n";
}

close $redirect;
close $people;
