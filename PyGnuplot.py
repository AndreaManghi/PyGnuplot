
'''
By Ben Schneider

Simple python wrapper for Gnuplot
Thanks to steview2000 for suggesting to separate processes,
    jrbrearley for help with debugging in python 3.4+

Special Thanks to ddip!
    This code was rewritten according to ddipp's suggestions resulting in
    a cleaner and better code and finnaly giving accesss to gnuplot returns
    thus allowing the use of the gnuplot fit function.

Also thanks to all the others who commented gave inputs and suggestions.

Example:
    from PyGnuplot import gp
    import numpy as np
    X = np.arange(10)
    Y = np.sin(X/(2*np.pi))
    Z = Y**2.0
    fig1 = gp()
    fig1.save([X,Y,Z])  # saves data into tmp.dat
    fig1.c('plot "tmp.dat" u 1:2 w lp)  # send 'plot instructions to gnuplot'
    fig1.c('replot "tmp.dat" u 1:3' w lp)
    fig1.pdf('myfigure.pdf')  # outputs pdf file

'''

import sys
from subprocess import PIPE, Popen
from threading import Thread
from time import sleep

try:
    from queue import Queue, Empty  # Python 3.x
except ImportError:
    from Queue import Queue, Empty  # Python 2.x

ON_POSIX = 'posix' in sys.builtin_module_names


class gp(object):
    """
    Desctiption:
        PyGnuplot object figure
    Inputs:
        gnuplot_address (Optional) : Desired gnuplot instance executable path, if not specified defaults to "gnuplot"
        terminal (Optional) : Desired terminal, if not specified uses gnuplot's default terminal
    Usage example:
        f1 = gp(r"C:\Program Files\gnuplot\bin\gnuplot.exe")
        pi = f1.a('print pi')

        Creates a gp object that uses the gnuplot instance installed in "C:\Program Files\gnuplot\bin\gnuplot.exe",
        executes "print pi" command with gnuplot and captures the output in the "pi" variable
    """

    def __init__(self, gnuplot_address='gnuplot', terminal=None):
        # Also initialize with gnuplot_address = r"C:\Program Files\gnuplot\bin\gnuplot.exe"
        self.gnuplot_address = gnuplot_address
        # open pipe with gnuplot
        self.p = Popen([gnuplot_address], stdin=PIPE, stderr=PIPE, stdout=PIPE,
                       bufsize=1, close_fds=ON_POSIX,
                       shell=False, universal_newlines=True)
        self.q_err = Queue()
        self.t_err = Thread(target=self.enqueue_std,
                            args=(self.p.stderr, self.q_err))
        self.t_err.daemon = True  # thread dies with the program
        self.t_err.start()
        self.q_out = Queue()
        self.t_out = Thread(target=self.enqueue_std,
                            args=(self.p.stdout, self.q_out))
        self.t_out.daemon = True  # thread dies with the program
        self.t_out.start()
        self.r()  # clear return buffer
        self.active_term = terminal or str(*self.a('print GPVAL_TERM'))
        self.c(f"set terminal {self.active_term}")

    def set_terminal(self, terminal: str):
        """
        Description:
            used to change active terminal
        Inputs:
            terminal : Name of the desired terminal
        Usage:
            set_terminal("svg")  # sets active terminal to "svg"
        """
        self.active_term = terminal
        self.c(f"set terminal {self.active_term}")

    def enqueue_std(self, out, queue):
        """
        Description:
            used to setup the queues for the return buffers
        """
        for line in iter(out.readline, ''):
            queue.put(line)
        out.close()

    def c(self, command):
        """
        Description:
            send a command to gnuplot.
            this does not check for responses
        Usage:
            w('plot sin(x)')  # only send a command to gnuplot
        """
        self.p.stdin.write(command + '\n')  # \n 'send return in python 2.7'
        self.p.stdin.flush()  # send the command in python 3.4+

    def r(self, vtype=str, timeout=0.05):
        """
        Description:
            read line without blocking, also clears the buffer.
        Usage:
            r()  # read response from gnuplot
        """
        lines = []
        while True:
            try:
                line = self.q_out.get(timeout=timeout)  # or .get_nowait()
                lines.append(vtype(line.strip()))
            except Empty:
                break
        return lines

    def a(self, command='', vtype=str, timeout=0.05):
        """
        Description:
            ask gnuplot (write and get answer), this function is blocking and waits for a response.
            If you need to execute a command with no output, or you want to send a command and get the answer later,
            use c() function.
            If you want to read the output with a non-blocking function use r() function
        Usage:
            pi = a('print pi')
            Executes 'print pi' command with gnuplot and returns command output into 'pi' variable
        """
        response = []
        self.c(command)
        while len(response) == 0:
            response = self.r(vtype, timeout)
        return response

    def m_str(self, data, delimiter=' '):
        """
        Description:
            turn data into string format
            this string format can be used when sending data to gnuplot
            usually via: plot "-" u 1:2 w lp
        """
        xy = list(zip(*data))
        ascii_st = ''
        for i in xy:
            for j in i:
                ascii_st += str(j) + delimiter
            ascii_st += '\n'
        return ascii_st

    def plot(self, data, com='plot "-" u 1:2 w lp'):
        """
        Description:
            quick plot data in gnuplot
            it basically pipes the data to gnuplot and plots it
        Default plot :
            com = "plot "-" u 1:2 w lp"
        """
        str_data = self.m_str(data)
        self.c(com)
        self.c(str_data+'e')  # add end character to plot string
        return self.r()

    def fit(self, data, func='y(x)=a + b*x', via='a,b', limit=1e-9, filename='tmp.dat', wait=1):
        """
        Description:
            simple quick way to fit with gnuplot
            this fit function temporarily stores the data in a file.
        Inputs:
            func : fitting function y(x) or f(x,y) or ...
            via : space separated variables to fit
            data : data set to fit
            filename : location where it can temporarily store its data
            wait : timing in s on how long to wait for the fit results
        Outputs:
            fit results in same order as via is defined
            report generated by gnuplot
        """
        self.save(data, filename=filename)
        func_name = func.split('=')[0]
        self.c(func)  # 'y(x)=a+b*x'
        self.c('set fit limit '+str(limit))
        self.c('fit ' + func_name + ' "' + filename + '" via ' + via)
        sleep(wait) # wait until fitting is done
        report = self.a() # if no report is returned maybe increase the wait time here
        return self.get_variables(via), report

    def fit2d(self, data, func='y(x)=a + b*x', via='a,b', limit=1e-9):
        '''
        Description:
            simple quick way to fit with gnuplot
        Inputs:
            func : fitting function y(x) or f(x,y) or ...
            via : space separated variables to fit
            data : data set to fit
        Outputs:
            fit results in same order as via is defined
            report generated by gnuplot
        '''
        str_data = self.m_str(data)
        func_name = func.split('=')[0]
        self.c(func)  # 'y(x)=a+b*x'
        self.c('set fit limit '+str(limit))
        self.c('fit ' + func_name + ' "-" via ' + via)
        report = self.a(str_data+'e')
        return self.get_variables(via), report

    def get_variables(self, via):
        """
        Description:
            returns values stored in gnuplot as given by via
        Inputs:
            via : for example via = 'a b c d e'
        Outputs:
            results in same order as via is given
        """
        vals = via.split(',')
        ret = []
        for i in vals:
            r = self.a('print ' + i)
            try:
                r = float(r[0])  # hard coded conversion if possible
            except ValueError:
                pass
            ret.append(r)
        return ret

    def save(self, data, filename='tmp.dat', delimiter=' '):
        """
        Description:
            saves numbers arrays and text into filename (default = 'tmp.dat)
            (assumes equal sizes and 2D data sets)
        Usage:
            s(data, filename='tmp.dat')  # overwrites/creates tmp.dat
        """
        with open(filename, 'w') as f:
            filestr = self.m_str(data, delimiter=delimiter)
            f.write(filestr)
            f.close()  # write the rest and close

    def empty_plot(self):
        self.c('clear')
        self.r()  # clear the output buffer

    def ps(self, filename='tmp.ps', width=14, height=9, fontsize=12):
        """
        Description:
            Script to make gnuplot print into a postscript file
        Usage:
            ps(filename='myfigure.ps')  # overwrites/creates myfigure.ps
        """
        self.c('set term postscript size '
               + str(width) + 'cm, '
               + str(height) + 'cm color solid '
               + str(fontsize) + " font 'Calibri';")
        self.c('set out "' + filename + '";replot;')
        self.c('set term ' + self.active_term + ';replot')
        return self.r()

    def pdf(self, filename='tmp.pdf', width=8.8, height=6, fontscale=0.5):
        """
        Description:
            Script to make gnuplot print into a pdf file
        Usage:
            pdf(filename='myfigure.pdf')  # overwrites/creates myfigure.pdf
        """
        self.c('set term pdfcairo fontscale '
               + str(fontscale) + 'size '
               + str(width) + 'cm, '
               + str(height) + "cm;")
        self.c('set out "' + filename + '";replot;')
        self.c('set term ' + self.active_term + '; replot')
        return self.r()  # clear buffer

    def quit(self):
        aa = self.a('exit')  # close gnuplot
        self.p.kill()  # kill pipe
        return aa


if __name__ == '__main__':
    # test functionality
    import numpy as np
    f1 = gp()
    x = np.linspace(0, 20, 1001)
    yn = np.random.randn(1001)/10
    y = np.sin(x)
    data = [x, y+yn]
    func = 'y(x) = a + b*cos(x + c)'
    (a, b, c), report = f1.fit(data, func, via='a,b,c', limit=1e-9)
    f1.save(data, "tmp.dat")
    f1.a('plot "tmp.dat" w lp')
    f1.a('replot y(x)')
    dat_s = f1.m_str([x, y], delimiter='\t')
    print()
    print("fitting function is: " + func)
    print("fit report:")
    for line in report:
        print(line)
