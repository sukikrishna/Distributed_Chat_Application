# Engineering Notebook

## JSON Wire Protocol Implementation

## Custom Wire Protocol Implementation

### Flow Diagram

## Wire Protocol Comparisons

--------------------------------------

## Day to Day Progress

#### Feb 7, 2025

We worked on starting the client-server chat application. We began by generating the initial starter code using ChatGPT, primarily for the JSON-based protocol, and incrementally modified it to align with the design requirements. Our implementation included a working protocol that allowed one client and one server to communicate, but several issues arose during testing.

We focused on refining our client-server chat application by debugging key functionalities, enhancing the GUI, and identifying improvements for multi-client interactions. Originally we were thinking of creating some kind of persistent storage for the database, but the application currently relies on an in-memory database, meaning data is lost when the server restarts. 

Some features of the application that were added by the end of work session is having the account listing only displays online/offline statuses without showing user interactions or unread messages. We also encountered errors when attempting to send messages to ourselves, as well as incorrect behavior in message deletion. Moving forward, we need to improve database persistence, fix GUI inconsistencies, and ensure seamless multi-client interactions across different systems.

##### Work Completed 

- Starter Code & Initial Setup
    - Used ChatGPT to generate base code for the JSON protocol version.
    - Modified code to meet design criteria and ensure basic client-server communication.
    - Established the initial message-passing structure and GUI layout using Tkinter.
- Testing & Debugging
    - Verified message sending and receiving between client and server.
    - Encountered and addressed message display inconsistencies.
    - Debugged the issue of messages not appearing correctly after being sent.
    - Identified that messages sent to oneself resulted in an unpacking error in refresh_messages().
    - Tested account deletion logic and confirmed that deleted accounts should not receive messages.
    - Found that message deletions were incorrectly displaying only the sender username instead of the message content.
- GUI Enhancements
    - Adjusted account listing to display usernames rather than only online/offline status.
    - Worked on improving user experience by showing the current logged-in username.
    - Implemented a search function for accounts, aiming for a Gmail-like database search.
    - Added a settings panel for account deletion, logging out, and configuring the number of messages displayed.
- Database & Cross-System Functionality
    - Determined that the application relies on an in-memory database, causing data loss on restart.
    - Identified the need to set up a remote SQL server for persistence and multi-client interactions.
    - Noted that the current design only allows interactions between users created on the same local server.
    - Found that accounts are tied to specific initialized ports, preventing smooth cross-system messaging.
- Next Steps
    - Fix self-messaging errors and improve message history display.
    - Improve GUI usability, including better message visualization and unread message tracking.
    - Enhance protocol efficiency by comparing JSON vs. custom protocol implementations.
    - Finalize documentation, including a README with instructions, and create demo visuals.

#### Feb 8, 2025

We focused on refining the structure of individual and group chats within our client-server messaging application. Our design evolved towards a more real-time messaging experience, similar to a chat application rather than an email system, with separate tabs for individual and group conversations. We implemented significant UI improvements, such as a dedicated settings page for configuring message display settings and logout options. While we made progress in organizing chat functionality, several issues remain with message history persistence, unread message tracking, and user account visibility.
We successfully integrated message passing for live communication but encountered difficulties in preserving chat history across logins. Additionally, the system does not automatically update the contacts list when new users are created, requiring a manual refresh or re-login to reflect changes. The unread message count is functional but does not dynamically update across sessions unless refreshed. Group chat functionality was structured such that all logged-in users could participate in a universal chatroom, rather than having selective group messaging.

Below are some UI design mockups of our chat application messaging features for users page and individual messaging components that we used as a guide for designing our application.

<p align="center">
  <img src="img/uiusers.png">
</p>

<p align="center">
  <img src="img/uichats.png">
</p>

##### Work Completed

- Refining Chat Structure
    - Designed the application to function more like a real-time chat rather than email.
    - Implemented separate chat threads for individual and group chats.
    - Ensured that unread messages are only stored if the recipient is on a different page or logged out.
    - Allowed real-time message display if the recipient is on the chat page.
    - Designed group chat as a single universal chatroom for all logged-in users, rather than allowing custom group selection.
- UI and Functional Enhancements
    - Created a settings page to manage the number of displayed messages and other account options.
    - Implemented a mechanism for logging in and switching between group and individual chat pages.
    - Allowed messages to be formatted as clickable elements, enabling deletion via selection.
    - Began work on implementing a refresh button to update the contacts list dynamically.
- Message Persistence and Handling
    - Identified that chat history is not preserved after logging out; messages should remain visible after re-login.
    - Found that the system currently displays all messages in the same window when switching between individual and group chats; messages need to be properly separated.
    - Started working on a way to selectively show only ‘n’ messages per chat window, based on user-defined settings.
- Fixes and Next Steps
    - Need to ensure newly created accounts are immediately reflected in the contacts list.
    - Add a notification popup when a user receives a message from someone they haven’t interacted with before.
    - Implement the ability to delete messages and chats properly while preserving unread message counts.
    - Ensure proper logout behavior and status updates for online/offline visibility.
    - Secure authentication by ensuring passwords are stored as hashed values rather than plaintext.
    - Add wildcard search functionality to allow users to search contacts efficiently.

#### Feb 9, 2025

We refined our chat application by simplifying its design to function more like Gmail, ensuring all incoming messages go straight to an unread messages section and eliminating the group chat feature. This decision helped streamline the interface while still meeting all design requirements. We now focus on maintaining proper message history, ensuring messages are saved correctly, and fixing message deletion inconsistencies.
We successfully implemented a basic framework where unread messages are distinct from read ones. However, we encountered issues where unread messages were incorrectly displayed in the history section, and message deletions were not updating correctly. To resolve this, we decided that the history tab should show the complete message history, while the "Check Unread Messages" feature should only display the latest n unread messages as defined by the hyperparameter. Additionally, we modified the users display to list all accounts and their status (online/offline), removing the dropdown selection for message recipients in favor of automatically filling in the recipient field when selecting a username.

Below is image of our original interface design and new design. Originally, can send messages to certain users here and see all incoming messages. Would click check messages in order to see the messages that have come in. there would be a popup on the UI indicating whether a new message was received by a user when the user is logged in, otherwise, at login there would be a popup indicating the number of unread messages.

<p align="center">
  <img src="img/chatusersold.png">
</p>

<p align="center">
  <img src="img/chatusersnew.png">
</p>

##### Work Completed

- Redesigning Message Handling
    - Simplified the messaging structure to function like Gmail.
    - Removed the group chat feature to focus on individual messaging.
    - Ensured all incoming messages go to the unread messages section until checked.
    - Established rules where history retains all messages, while "Check Unread Messages" only displays the latest n unread messages.
- Fixing Message Persistence & Display
    - Addressed issues where unread messages were appearing in history before being checked.
    - Ensured messages appear in the correct order (previously displayed inconsistently in chronological or reverse order).
    - Began work on implementing a mechanism to display only n messages at a time, based on user-defined settings.
- Enhancing User Interface & Experience
    - Adjusted the users display to show all accounts and their online/offline status.
    - Removed dropdown selection for recipients; instead, the recipient field is automatically filled when a username is selected.
    - Planned a refresh button to update new accounts and status changes dynamically.
- Bug Fixes & Functionality Improvements
    - Worked on pop-up notifications for receiving new messages while on different pages (e.g., login or users tab).
    - Addressed message deletion issues to ensure they properly disappear from chat history.
    - Began testing hosting the application on multiple devices to support cross-system communication.
    - Explored using different data formats for the custom protocol (e.g., JSON vs. strings/bytes/binary).
- Next Steps
    - Implement and test the n message display limit to ensure smooth pagination.
    - Finalize message deletion logic to remove messages correctly from all relevant sections.
    - Enable real-time updates for account status and unread message count.
    - Complete the comparison of JSON vs. custom protocol, measuring data size and transfer efficiency.
    - Continue debugging message read/unread logic to ensure accuracy when switching between tabs.

#### Feb 10, 2025

We focused on refining message handling, improving user experience, and preparing for hosting on multiple devices. We addressed several key issues, including message order consistency, tracking unread messages properly, and ensuring deleted accounts do not interfere with the messaging system. We also worked on implementing an automatic IP retrieval system for smoother multi-device connectivity and refining our documentation for better usability.
A major milestone was refining our approach to unread and read messages. Messages now transition correctly from unread to history only after they have been checked, with ordering now consistent from oldest to newest by default (with an option to reverse this in settings). Additionally, we made progress toward fully integrating both JSON and custom protocols, ensuring they align with the application's core messaging structure. The custom protocol right now, needs the most work in terms of implementation because the UI is working, but we continue to get server connection errors and some of the functionalities wouldn’t work anymore. Moreover, there were problems with the wire protocol in terms of how messages would be encoded and decoded wouldn’t work properly.

##### Work Completed

- Message Handling Improvements
    - Ensured messages sent to deleted accounts are handled properly (i.e., sender receives a notification that the user does not exist).
    - Refactored message order so it consistently displays from oldest to newest (by default).
    - Implemented an option to toggle between oldest-to-newest and newest-to-oldest sorting in the settings panel.
    - Fixed unread messages so they only move to history after being explicitly checked.
    - Ensured the pop-up notification for new messages correctly reflects the number of unread messages, both while logged in and when logging back in.
- Multi-Device Hosting & Networking
    - Researched firewall and WiFi issues related to hosting on two separate devices.
    - Implemented a script to auto-detect the local IP address instead of relying on hardcoded values.
    - Clarified documentation regarding IP configuration for Windows and Linux/WSL2.
    - Ensured the server passes the correct port to the client for security reasons.
    - Investigated and tested different methods for running the application on multiple machines.
- UI & Display Enhancements
    - Updated the user list to reflect online/offline status accurately and immediately when an account is created or deleted.
    - Added logic to auto-update the display when an account is deleted without requiring a manual refresh.
    - Improved the "To:" field in the message composition area to be inline instead of separate lines.
    - Addressed minor UI glitches, including adjusting message counts to update in real-time.
- Protocol & Logging Enhancements
    - Continued merging implementations of JSON and custom protocols.
    - Measured and compared data transfer efficiency between JSON and a custom string-based protocol.
    - Ensured logs reset correctly when the server closes.
    - Began preparing for demo GIFs showcasing key functionalities.
    - Added version tracking for message packets to maintain backward compatibility with future updates.
- Next Steps & Remaining Issues
    - Complete hosting setup to work seamlessly across multiple devices.
    - Finalize merging the JSON and custom protocol implementations.
    - Ensure new accounts appear instantly in the contact list without requiring a full refresh.
    - Address security concerns related to storing passwords (move to proper hashing mechanism).
    - Add a wildcard search function for filtering contacts.
    - Review and refine documentation, including engineering notebook updates and final demo preparations.

#### Feb 11, 2025

Today, we focused on rebuilding the custom protocol implementation, refining message encoding/decoding, and ensuring the distributed system functioned across multiple devices. Initially, the previous custom protocol scripts were not working properly, causing server connection errors that prevented basic functionality like creating and logging into accounts. To resolve this, we started over by generating a rough outline of the custom protocol based on the JSON scripts, preserving all UI and interactive features while focusing solely on fixing message passing. This approach allowed us to verify account creation, login, logout, deletion, and user search functionality before tackling packet transmission issues.
Once the UI and core features were confirmed to be working, we shifted focus to debugging the custom protocol’s message encoding and decoding. The primary issue was an incorrect byte allocation when passing packets, which led to parsing errors where messages were not decoded correctly. The struct library was used to convert data into binary format, but our original encoding scheme was overly complex. Instead of including version numbers, operation codes, and other metadata as initially planned, we simplified the encoding structure to use only three fields: header, message length, and message. This change improved stability, and we manually verified that all fields were encoded and decoded correctly, resolving prior errors related to incorrect byte allocations.
With message passing successfully implemented, we tested the system across multiple devices, confirming that distributed messaging worked as intended. The final steps involved refining the repository, adding test code and documentation, and improving how the scripts were executed. We updated the code so that the application could be run with a single command-line instruction using flags, removing the need to manually navigate directories. Additionally, we included a configuration file that automatically updates with the correct port and added functionality to detect and store the user's local IP address in Windows, making setup easier for new users.

Below is example of how incoming messages were being decoded incorrectly.

<p align="center">
  <img src="img/incorrectdecoding.png">
</p>

##### Work Completed

- Rebuilding the Custom Protocol Implementation
    - Recreated the custom protocol scripts using a modified version of the JSON protocol, preserving UI and interactive elements.
    - Ensured basic features such as login, logout, account creation, and search worked before addressing message-passing issues.
- Fixing Message Encoding & Decoding Issues
    - Investigated struct library usage and how binary data was being packed and unpacked.
    - Simplified encoding to use three fields: header, message length, and message.
    - Identified incorrect byte allocations that caused message parsing issues and manually verified all encoded fields.
    - Successfully implemented message passing with proper decoding.
- Distributed System Testing
    - Ran the system across multiple devices to confirm message passing worked correctly.
    - Addressed issues related to incorrect message parsing when messages were shorter than allocated packet memory.
- Repository Cleanup & Execution Enhancements
    - Added test code and documentation to improve usability.
    - Implemented a single command-line execution method using flags to specify client/server and protocol type.
    - Ensured configuration updates dynamically with the correct port.
    - Added code to auto-detect and store the user’s local IP address for Windows users.
- Next Steps & Remaining Tasks:
    - Finalize protocol comparison (JSON vs. custom) by measuring message size and transmission efficiency.
    - Add more test cases to validate edge scenarios in message encoding/decoding.
    - Complete demo videos and README documentation for submission.
    - Ensure logs reset correctly after the server closes.

#### Feb 12, 2025

We primarily focused on finalizing the documentation, adding test cases, and ensuring that the command-line execution system worked as intended in preparation for giving the demo in class today. Our main goal was to streamline the usability of the application so that users could run the appropriate client or server script based on command-line flags without manually navigating directories or modifying configuration files.
We confirmed that the script correctly used the os module to internally call the relevant server or client execution, automatically selecting the correct protocol (JSON or custom) and assigning the correct host and port. Additionally, we prioritized command-line arguments over config file values, ensuring flexibility while still allowing users to specify settings via configuration if needed.

##### Work Completed

- Finalizing Documentation & Usability Improvements
    - Completed README.md with setup instructions, flag usage, and example commands.
    - Clarified protocol details, including JSON vs. custom protocol differences.
    - Ensured documentation explained how local IP addresses are handled dynamically.
- Testing & Debugging Execution Flow
    - Double-checked that scripts correctly launch the server and client without requiring users to navigate directories manually.
    - Ensured flags (--client/--server, --json/--custom, --host, --port) were correctly parsed and applied.
    - Verified that command-line arguments take precedence over config file values.
- Adding & Running Tests
    - Implemented basic unit tests to validate message encoding and decoding for both protocols.
    - Added test cases to check for edge cases in message parsing, including handling incorrect byte lengths.
    - Verified that the message sorting options (oldest-to-newest, newest-to-oldest) functioned as expected.
- Repository Cleanup & Final Adjustments
    - Ensured that all necessary files were included in the repository before final submission.
    - Checked that the logging system resets correctly when restarting the server.
    - Reviewed error handling and added meaningful error messages for common issues (e.g., missing arguments, invalid protocol selection).

#### Feb 13, 2025

We cleaned up the code for the final submission and worked on the code review and cleaning up the engineering notebook to format it nicely.

##### Work Completed

    - Fixed the version number issue in the code and added proper checks
    - Cleaned up and reformatted the engineering notebook
    - Wrote a proper code review based on the detailed notes that we took for each team.
