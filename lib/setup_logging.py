import logging

def setup_logging(program_name,logfile=None):

    if logfile:
        logging.basicConfig(\
            filename=logfile,\
            level=logging.INFO,\
            format="%(asctime)s | {} | %(levelname)s: [%(name)s] %(message)s".format(program_name),\
            datefmt='%Y%m%d%H%M%S'
        )
    else:
        logging.basicConfig(\
            level=logging.INFO,\
            format="%(asctime)s | {} | %(levelname)s: [%(name)s] %(message)s".format(program_name),\
            datefmt='%Y%m%d%H%M%S'
        )
