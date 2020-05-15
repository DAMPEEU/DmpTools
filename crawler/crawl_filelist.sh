#!/bin/bash
# RELIES ON $CRAWLER_ROOT variable

if [ -z $CRAWLER_ROOT ]
then
	echo "Error! Variable CRAWLER_ROOT not set. Exiting..."
	exit 1
fi

release="latest"
infile=$1
global_badfile=$2

infile_base="${infile%.*}"  # Remove file extension

ofile=${infile_base}.json
errfile=${infile_base}.err
badfile_tmp=${ofile/".json"/".bad"}

rm -v ${errfile} ${badfile_tmp}

if grep -q "CentOS" /etc/redhat-release
then
	source /cvmfs/dampe.cern.ch/centos7/etc/setup.sh
	echo "Sourcing DAMPE for Centos7"
else
	source /cvmfs/dampe.cern.ch/rhel6-64/etc/setup.sh
	echo "Soucing DAMPE for SL6"
fi
dampe_init ${release}

for f in $(cat ${infile});
do
    python ${CRAWLER_ROOT}/crawler.py ${f} -o ${ofile} 2> ${errfile}
    RC1=$?
done

python ${CRAWLER_ROOT}/analyze.py ${ofile} ${badfile_tmp} 2>> ${errfile}
RC2=$?

if [ -f ${badfile_tmp} ];
then
    cat ${badfile_tmp} >> ${global_badfile}
fi

python ${CRAWLER_ROOT}/errorcodes.py ${ofile}
RC3=$?

RC=$(( RC1 + RC2 + RC3 ))

exit ${RC}
