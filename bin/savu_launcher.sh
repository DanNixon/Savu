module load global/cluster

echo "running the mpi job" 

savupath=$1
datafile=$2
processfile=$3
outpath=$4
outname=$5
nNodes=$6
nCPUs=$7

filepath=$savupath/bin/savu_mpijob.sh
M=$((nNodes*12))
echo $M
echo "qsub -N $outname -sync y -j y -pe openmpi $M -q medium.q@@com06 $filepath $savupath $datafile $processfile $outpath $nCPUs > tmp.txt"


filename=`echo $outname.o`
jobnumber=`awk '{print $3}' tmp.txt | head -n 1`
filename=$filename$jobnumber
echo $filename

while [ ! -f $filename ]
do
  sleep 2
done

cat $filename

grep "L " $filename > log_$filename

#sleep 20
#echo qacct -j ${jobnumber}
#qacct -j ${jobnumber}

