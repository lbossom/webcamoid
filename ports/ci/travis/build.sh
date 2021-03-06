#!/bin/bash

if [ -z "${DISABLE_CCACHE}" ]; then
    if [ "${CXX}" = clang++ ]; then
        UNUSEDARGS="-Qunused-arguments"
    fi

    COMPILER="ccache ${CXX} ${UNUSEDARGS}"
else
    COMPILER=${CXX}
fi

if [ "${TRAVIS_OS_NAME}" = linux ] && [ -z "${ANDROID_BUILD}" ]; then
    EXEC="docker exec ${DOCKERSYS}"
fi

BUILDSCRIPT=dockerbuild.sh

if [ "${DOCKERIMG}" = ubuntu:xenial ]; then
    cat << EOF > ${BUILDSCRIPT}
#!/bin/bash

source /opt/qt${PPAQTVER}/bin/qt${PPAQTVER}-env.sh
EOF

    chmod +x ${BUILDSCRIPT}
fi

if [ "${ANDROID_BUILD}" = 1 ]; then
    export PATH=$PWD/build/Qt/${QTVER}/android_${TARGET_ARCH}/bin:$PATH
    export ANDROID_NDK_ROOT=$PWD/build/android-ndk-${NDKVER}
    qmake -spec ${COMPILESPEC} Webcamoid.pro \
        CONFIG+=silent
elif [ "${TRAVIS_OS_NAME}" = linux ]; then
    export PATH=$HOME/.local/bin:$PATH

    if [ "${DOCKERSYS}" = debian ]; then
        if [ "${DOCKERIMG}" = ubuntu:xenial ]; then
           cat << EOF >> ${BUILDSCRIPT}
qmake -spec ${COMPILESPEC} Webcamoid.pro \
    CONFIG+=silent \
    QMAKE_CXX="${COMPILER}"
EOF
            ${EXEC} bash ${BUILDSCRIPT}
        else
            ${EXEC} qmake -qt=5 -spec ${COMPILESPEC} Webcamoid.pro \
                CONFIG+=silent \
                QMAKE_CXX="${COMPILER}"
        fi
    else
        ${EXEC} qmake-qt5 -spec ${COMPILESPEC} Webcamoid.pro \
            CONFIG+=silent \
            QMAKE_CXX="${COMPILER}"
    fi
elif [ "${TRAVIS_OS_NAME}" = osx ]; then
    ${EXEC} qmake -spec ${COMPILESPEC} Webcamoid.pro \
        CONFIG+=silent \
        QMAKE_CXX="${COMPILER}" \
        LIBUSBINCLUDES=/usr/local/opt/libusb/include \
        LIBUVCINCLUDES=/usr/local/opt/libuvc/include \
        LIBUVCLIBS=-L/usr/local/opt/libuvc/lib \
        LIBUVCLIBS+=-luvc
fi

if [ -z "${NJOBS}" ]; then
    NJOBS=4
fi

${EXEC} make -j${NJOBS}
