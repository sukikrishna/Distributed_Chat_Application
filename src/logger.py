import logging

class Logger:
    """Handles logging operations for the chat application."""
    
    def __init__(self, log_file='chat.log'):
        """Initializes the logger.
        
        Sets up logging configurations including the log file location
        and logging level.
        
        Args:
            log_file (str): Path to the log file.
        """
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger()
    
    def log(self, message, level='info'):
        """Logs a message at the specified logging level.
        
        Args:
            message (str): The log message.
            level (str): The severity level of the log message. Options are:
                - 'info'
                - 'error'
                - 'warning'
                - 'debug'
        """
        if level == 'info':
            self.logger.info(message)
        elif level == 'error':
            self.logger.error(message)
        elif level == 'warning':
            self.logger.warning(message)
        elif level == 'debug':
            self.logger.debug(message)
