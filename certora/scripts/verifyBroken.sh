#!/bin/sh

if test -n "$1"
then
    RULE="--rule $1"
fi

certoraRun \
    certora/conf/broken.conf \
    $RULE \
    --msg "Broken CPP verification $RULE $2" \

