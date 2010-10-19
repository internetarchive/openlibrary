#!/usr/bin/perl
use strict;
use warnings;

use Net::FTP;

my $host = 'rs7.loc.gov';
open my $fh, '/home/edward/.olrc' or die $!;
my %auth;
while (<$fh>) {
    /^lc_update_(user|pass) = '(.*)'$/ and $auth{$1} = $2;
}
close $fh;

my $dir = '/emds/books/all';
my $out_dir = '/1/edward/lc_updates/';

print "connecting to host: $host\n";
my $ftp = Net::FTP->new($host) or die "Cannot connect to some.host.name: $@";
$ftp->login($auth{user}, $auth{pass}) or die "Cannot login ", $ftp->message;
print "login complete\n";
$ftp->binary() or die $ftp->message;
$ftp->cwd($dir) or die "Cannot change working directory ", $ftp->message;
my @ls = $ftp->ls() or die "ls failed ", $ftp->message;
my $download_num = 0;
chdir $out_dir;
for (@ls) {
    -e $_ and next;
    $download_num++;
    print "$_\n";
    $ftp->get($_) or die $ftp->message;
}

$ftp->quit;

print "$download_num\n";
