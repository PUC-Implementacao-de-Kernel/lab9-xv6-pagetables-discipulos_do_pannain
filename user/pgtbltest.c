#include "kernel/types.h"
#include "user/user.h"

int
main(int argc, char *argv[])
{
  (void)argc;
  (void)argv;

  int pid = getpid();
  int upid = ugetpid();
  printf("pgtbltest: getpid=%d ugetpid=%d\n", pid, upid);
  if(pid != upid){
    fprintf(2, "pgtbltest: ugetpid retornou pid incorreto\n");
    exit(1);
  }
  printf("pgtbltest: ugetpid ok\n");

  printf("pgtbltest: chamando kpgtbl()\n");
  if(kpgtbl() < 0){
    fprintf(2, "pgtbltest: kpgtbl falhou\n");
    exit(1);
  }
  printf("pgtbltest: fim\n");
  exit(0);
}
