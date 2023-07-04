#!/bin/sh

if test -n "$1"
then
    RULE="--rule $1"
fi

certoraRun \
    certora/conf/fixed.conf \
    $RULE \
    --msg "Fixed CPP verification $RULE $2" \

