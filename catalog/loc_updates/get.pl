use strict;
use warnings;

use Net::FTP;

my %auth = do '../account';

my $dir = '/emds/books/all';

my $ftp = Net::FTP->new($auth{host}) or die "Cannot connect to $auth{host}: $@";
$ftp->login($auth{user}, $auth{pass}) or die "Cannot login ", $ftp->message;
$ftp->binary() or die $ftp->message;
$ftp->cwd($dir) or die "Cannot change working directory ", $ftp->message;
my @ls = $ftp->ls() or die "ls failed ", $ftp->message;
my $download_num = 0;
for (@ls) {
    -e $_ and next;
    $download_num++;
    $ftp->get($_) or die $ftp->message;
}

$ftp->quit;

print $download_num;
