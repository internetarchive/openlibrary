#!/usr/bin/perl

use strict;
use warnings;
use IO::Handle;
use MARC::Charset 'marc8_to_utf8';
use Text::Netstring qw(netstring_encode netstring_decode netstring_verify netstring_read);
use Encode 'encode_utf8';

my $input = new IO::Handle;
$input->fdopen (fileno (STDIN),"r");

my $output = new IO::Handle;
$output->fdopen (fileno (STDOUT), "w");
$output->autoflush (1);

while (!$input->eof) {
	my $ns = netstring_read ($input);
	die "read error" unless defined ($ns);
	last unless $ns;
	
	my $s_marc8 = netstring_decode ($ns);

	my $error = 0;
	$SIG{__WARN__} = sub {
		$error = $_[0];
		chomp $error;
	};
	my $s_unicode = marc8_to_utf8 ($s_marc8);
	delete $SIG{__WARN__};
	if ($error) {
		$output->print (netstring_encode ("-$error"));
	} else {
		my $s_utf8_bytes = encode_utf8 ($s_unicode);
		$output->print (netstring_encode ("+$s_utf8_bytes"));
	}
	$output->flush ()
}
