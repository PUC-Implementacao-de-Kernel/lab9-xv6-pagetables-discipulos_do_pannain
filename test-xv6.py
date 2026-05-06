#!/usr/bin/env python3

#
# python script that tests xv6 without having to boot it and type to its shell
#
# ./test-xv6.py usertests  (runs usertests)
# ./test-xv6.py -q usertests (runs the quick tests of usertests)
# ./test-xv6.py crash  (runs the crash tests)
# ./test-xv6.py log (runs the log crash test)

import argparse, os, inspect, re, signal, subprocess, sys, time
from subprocess import run

parser = argparse.ArgumentParser()
parser.add_argument('testrex', help="test name or regular expression")
parser.add_argument("-q", action='store_true', help="usertests quick")
args = parser.parse_args()

class QEMU(object):

    def __init__(self, reset=False, cpus=None):
        if reset:
            self.build_xv6()
            self.reset_fs()
        q = ["make"]
        if cpus:
            q.append("CPUS=%d" % cpus)
        q.append("qemu")
        self.proc = subprocess.Popen(q, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT)
        self.output = ""
        self.outbytes = bytearray()       
        time.sleep(1)

    def reset_fs(self):
        try:
            run(["rm", "fs.img"], check=True)
            run(["make", "fs.img"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Command failed with exit code {e.returncode}")

    def build_xv6(self):
        try:
            run(["make", "kernel/kernel"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Command failed with exit code {e.returncode}")

    def save_output(self):
      try:
        with open("test-xv6.out", "w") as f:
            f.write(self.output)
            f.close()
      except OSError as e:
        print("Provided a bad results path. Error:", e)     
        
    def cmd(self, c):
        if isinstance(c, str):
            c = c.encode('utf-8')
        self.proc.stdin.write(c)
        self.proc.stdin.flush()
        
    def crash(self):
        ps = run(['ps', '-opid', '--no-headers', '--ppid', str(self.proc.pid)], stdout=subprocess.PIPE, encoding='utf8')
        kids = [int(line) for line in ps.stdout.splitlines()]
        if len(kids) == 0:
            print("no qemu")
            os.exit(1)
        print("kill", kids[0])
        os.kill(kids[0], signal.SIGKILL)

    def stop(self):
        ps = run(['ps', '-opid', '--no-headers', '--ppid', str(self.proc.pid)],
                 stdout=subprocess.PIPE, encoding='utf8')
        for line in ps.stdout.splitlines():
            try:
                os.kill(int(line), signal.SIGTERM)
            except ProcessLookupError:
                pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def read(self):
        buf = os.read(self.proc.stdout.fileno(), 4096)
        self.outbytes.extend(buf)
        self.output = self.outbytes.decode("utf-8", "replace")

    def lines(self):
        return self.output.splitlines()

    def error(self):
        print("FAIL: match failed", regexps)
        self.save_output()
        self.stop()
        sys.exit(1)

    def fail(self, msg):
        print("FAIL:", msg)
        self.save_output()
        self.stop()
        sys.exit(1)

    def match(self, *regexps, exit=True):
        lines = self.lines()
        last = -1
        for i, line in enumerate(lines):
            if any(re.match(r, line) for r in regexps):
                print(line)
                last = i
        if last == -1 and exit:
            self.error()
        l = ""
        if last >= 0:
            l = lines[last]
        return last >= 0, l

    def monitor(self, *regexps, progress="", timeout):
        deadline = time.time() + timeout
        while True:
            time.sleep(1)
            timeleft = deadline - time.time()
            if timeleft < 0:
                self.error()
            self.read()
            ok, _ = self.match(*regexps, exit=False)
            if ok:
                return
            ok, line = self.match(progress, exit=False)
            if ok:
                print(line)

def crash_log():
    q = QEMU(True)
    q.cmd("logstress f0 f1 f2 f3 f4 f5\n")
    time.sleep(2)
    q.crash()
    q.stop()

def recover_log():
    q = QEMU()
    time.sleep(2)
    q.read()
    ok, _ = q.match('^recovering', exit=False)
    if ok:
        q.cmd("ls\n")
        time.sleep(2)
        q.read()
        q.match('f5')
    q.stop()
    return ok

def forphan():
    q = QEMU(True)
    q.cmd("forphan\n")
    time.sleep(5)
    q.read()
    q.match('wait')
    q.crash()
    q.stop()

def dorphan():
    q = QEMU(True)
    q.cmd("dorphan\n")
    time.sleep(5)
    q.read()
    q.match('wait')
    q.crash()
    q.stop()

def recover_orphan():
    q = QEMU()
    time.sleep(2)
    q.read()
    q.match('^ireclaim')
    q.stop()

def test_log():
    print("Test recovery of log")
    for i in range(5):
        crash_log()
        ok = recover_log()
        if ok:
            print("OK")
            return
        print("log attempt ", i+1)
    print("FAIL")
    sys.exit(1)
    
def test_forphan():
    print("Test recovery of an orphaned file")
    forphan()
    recover_orphan()
    print("OK")

def test_dorphan():
    print("Test recovery of an orphaned file")
    dorphan()
    recover_orphan()
    print("OK")

def test_crash():
    test_log()
    test_forphan()
    test_dorphan()

def test_usertests(test=""):
    timeout = 600
    opt = ""
    if args.q:
        opt = " -q"
        timeout = 300
    elif test != "":
        opt += " " + test
    q = QEMU(True)
    q.cmd("usertests" + opt + "\n")
    q.monitor('^ALL TESTS PASSED', progress='test', timeout=timeout)
    q.stop()

def test_pagetable():
    print("Test page table printing")

    q = QEMU(True, cpus=1)
    q.cmd("pgtbltest\n")
    q.monitor('^pgtbltest: fim$', timeout=15)

    if not re.search(r'^pgtbltest: ugetpid ok$', q.output, re.M):
        q.fail("ugetpid nao retornou o mesmo valor de getpid")

    if "TODO: implemente vmprint" in q.output:
        q.fail("vmprint ainda esta como stub")

    if not re.search(r'^page table 0x[0-9a-f]+$', q.output, re.M):
        q.fail("vmprint nao imprimiu o cabecalho esperado")

    lines = [line for line in q.output.splitlines()
             if re.match(r'^(\.\. )+\d+: va 0x[0-9a-f]+ pte 0x[0-9a-f]+ pa 0x[0-9a-f]+$', line)]
    if len(lines) < 6:
        q.fail("vmprint imprimiu poucas PTEs validas")

    if not any(line.startswith(".. .. ..") for line in lines):
        q.fail("vmprint nao imprimiu entradas no nivel folha")

    usys_line = next((line for line in lines
                      if " va 0x0000003fffffd000 " in line), None)
    if usys_line is None:
        q.fail("vmprint nao mostrou a entrada de USYSCALL")

    m = re.search(r' pte 0x([0-9a-f]+) ', usys_line)
    if m is None:
        q.fail("nao foi possivel ler a PTE de USYSCALL")
    pte = int(m.group(1), 16)
    if (pte & 0x2) == 0:
        q.fail("USYSCALL nao esta mapeada com PTE_R")
    if (pte & 0x10) == 0:
        q.fail("USYSCALL nao esta acessivel ao usuario com PTE_U")
    if (pte & 0x4) != 0:
        q.fail("USYSCALL foi mapeada com permissao de escrita")

    if not any(" va 0x0000003fffffe000 " in line for line in lines):
        q.fail("vmprint nao mostrou a entrada de TRAPFRAME")

    if not any(" va 0x0000003ffffff000 " in line for line in lines):
        q.fail("vmprint nao mostrou a entrada de TRAMPOLINE")

    q.stop()
    print("OK")

def main():
    print(args)
    rex = r'%s' % args.testrex
    funcs = [(obj,name) for name,obj in inspect.getmembers(sys.modules[__name__]) 
                     if (inspect.isfunction(obj) and 
                         name.startswith('test'))]
    none = True
    for (f,n) in funcs:
        if re.search(rex, n):
            none = False
            f()
    if none:
        test_usertests(test=args.testrex)

main()
