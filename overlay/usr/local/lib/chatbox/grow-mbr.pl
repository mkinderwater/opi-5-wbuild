use strict;use warnings;
my ($disk,$total,$sysstart,$id)=@ARGV;
die "Invalid disk geometry\n" unless $total =~ /^\d+$/ && $sysstart =~ /^\d+$/;
open(my $f,'+<',$disk) or die "Cannot open NVMe disk\n";
binmode($f);read($f,my $m,512)==512 or die "Cannot read MBR\n";
die "Invalid MBR signature\n" unless substr($m,510,2) eq "\x55\xaa";
die "Disk identity mismatch\n" unless sprintf('%08x',unpack('V',substr($m,440,4))) eq $id;
my ($s1,$n1)=unpack('VV',substr($m,454,8));
my ($s2,$n2)=unpack('VV',substr($m,470,8));
die "Unexpected partition layout\n" unless ord(substr($m,450,1))==12 && ord(substr($m,466,1))==131
 && $s1==2048 && $n1==131072 && $s2==133120 && $s2==$sysstart;
die "Extra partitions present\n" unless substr($m,478,32) eq "\0"x32;
my $n=$total-$s2;
die "Unsafe resize geometry\n" unless $n >= $n2 && $n<=0xffffffff;
seek($f,474,0) or die "Seek failed\n";
print $f pack('V',$n) or die "Write failed\n";
close($f) or die "Commit failed\n";
