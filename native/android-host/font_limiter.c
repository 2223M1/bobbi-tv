/* Limit a separately owned font decoder, never the Kodi process. */
#include <sys/resource.h>
#include <unistd.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    char executable[PATH_MAX], decoder[PATH_MAX];
    if (argc < 3 || !realpath(argv[0], executable) || !realpath(argv[1], decoder)) return 2;
    char *a = strrchr(executable, '/'), *b = strrchr(decoder, '/');
    if (!a || !b || strcmp(b+1, "libbobbi_7zip.so")) return 2;
    *a = 0; *b = 0;
    if (strcmp(executable, decoder)) return 2;
    struct rlimit memory = {192*1024*1024, 192*1024*1024};
    struct rlimit file = {32*1024*1024, 32*1024*1024};
    struct rlimit cpu = {20, 20};
    if (setrlimit(RLIMIT_AS, &memory) || setrlimit(RLIMIT_FSIZE, &file) || setrlimit(RLIMIT_CPU, &cpu)) return 3;
    (void)nice(19);
    execv(argv[1], argv+1);
    return 4;
}
