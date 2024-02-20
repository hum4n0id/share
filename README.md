# Layer 4 (TCP) Load-Balancing Server and Library

This document outlines the design and architecture of a TCP load-balancer/reverse proxy and its associated library. The server accepts TLS connections from clients, authenticates them using client certificates, and forwards requests to upstream servers based on the client certificate's organization field. This is broken out into a modular library and the actual load balancing server. The library provides the necessary components for upstream server management and selection and client rate limiting, while the load balancing server supports mTLS authentication, client organization authorization, connection handling, and client forwarding to upstream servers.

## Library Design

#### Components

- **Upstream Server Pool**:
  - Manages a pool of upstream servers, including their addresses and connection counts.
  - Upstream servers are broken out into subgroups to facilitate the server authorization scheme: i.e., groupA, groupB, groupC.
  - Clients are directed to the appropriate subgroup based on the client certificate organization field, which matches the subgroup naming convention.

- **Forwarder/Load Balancer**:
  - Manages the forwarding logic, choosing the upstream server with the least number of connections.
  - Utilizes a static array of n<10 upstream servers, sorted by their connection count, in order to facilitate selecting the least connected upstream server.
  - Clients are only forwarded to their matching upstream subgroup and assigned the least connected upstream within that group.

- **Rate Limiter**:
  - Implements rate limiting based on a fixed window algorithm.
  - Limits the number of requests a client can make within a designated time window.
  - Provides a garbage collection goroutine to clean up expired client entries outside of the designated time window.

#### Key Library Types

- **Server Struct**:
  - Represents a upstream server with fields for address and connection count.

- **ServerPool Struct**:
  - Represents the group of upstream servers that the requesting client can connect to.

- **Forwarder Struct**:
  - Provides methods for selecting the least connected upstream server and decrementing connection counts.

- **RateLimiter Struct**:
  - Implements fixed-window rate limiting logic with methods to check and enforce client request rates within a given window of time.
  - Catalogs client attempted/successful connections with timestamps.
  - Includes a method to instantiate a garbage collector to clean up expired rate limiting data.

## Reverse Proxy / Load-Balancing Server Design

### Components

- **TLS Configuration Loader**:
  - Loads the necessarry load-balancer server certificates stored on the local filesystem.
  - Establishes the mutual TLS exchange with client certs sharing the same signing authority (CA) as the server cert.

- **Upstream Pool Initializer**:
  - Initializes the upstream server pool and rate limiter for the forwarder.

- **Rate-Limiter Initializer**:
  - Initializes the rate-limiter to track and throttle client connections, originating from their clientID field. 

- **Connection Handler**:
  - Manages incoming connections by performing TLS handshakes and extracting client information from certificates.
  - Parses client certificates to extract the `CommonName` as the client ID (clientID) and the `Organization` as the client org (clientOrg).
  - Authorizes clients based on predefined rules mapping the client organization to upstream server groups.
  - Determines the appropriate upstream server to forward the request based on the client's organization.

- **Client Forwarding**:
  - Forwards the client's TCP connection to the selected upstream server.
  - Passes through application data between client and upstream server. Basic HTTP GET is supported to confirm the client has reached a matching upstream, relaying the upstream server response to the client.

- **Client Acceptance Loop**:
  - Continuously accepts new client connections and handles them using goroutines.

- **Graceful Shutdown Handler**:
  - Listens for interrupt signals and gracefully shuts down the load-balancer server and rate limiter.

## Algorithms

Here are the core algorithms used in the load balancing library to support the load-balancing server:

- **Least-Connected Upstream Selection**:
  - The server selection is based on a least-connection approach. A static array keeps track of the connection count for each server.
  - The array is sorted, and the server with the fewest connections is selected to handle incoming requests.
  - This approach ensures an even distribution of load across the servers.
  - Caveat: scalability is limited - as we are bound to a worst-case of O(n). Performance linearly degrades with upstream server scale.

- **Rate Limiting**:
  - A fixed window rate limiting algorithm is used to control the rate at which clients can make requests.
  - Clients are associated with a counter and a timestamp. If the counter exceeds the threshold within the time window, new requests are blocked until the window resets.
  - Caveat: this algorithm is simple and efficient but might allow bursts of traffic at the window's edges.

- **Rate Limiter Cleanup**:
  - Expired rate limiting data is cleaned up using a garbage collection goroutine that runs periodically.
  - This routine scans the data structure for expired entries and removes them for basic housekeeping.

These algorithms are critical for maintaining the server's performance and reliability.

## Concurrency, Synchronization and Cleanup

Concurrency, synchronization, and garbage collection are handled in the following ways to ensure the server operates efficiently and safely:
- Both the lb server and the library make use of goroutines to handle multiple client connections.
- Go syncronization primitives, such as mutexes (`sync.Mutex`), are utilized to protect shared data structures (such as connection count and timestamp maps) from concurrent access, preventing data races and race conditions.
- A cleanup mechanism via garbage collection is employed to ensure time-series client connection tracking in the rate limiter is appropriately managed. This is run in a goroutine and utilizes a stop channel as part of the shutdown process.
- A general shutdown sequence will ensure that the lb server stops accepting new connections and that existing connections are handled properly before the application exits.

## Error Handling

The server and library include error handling for various scenarios:
- TLS handshake failures.
- Missing or invalid client certificates.
- Upstream server selection failures.
- Forwarding logic errors.
- Rate limiting violations.
- Connection errors during forwarding.
- Additional error handling will be employed when appropriate during the implementation phase.

## Security

The server implements mutual TLS to authenticate clients and ensure encrypted communication. Client authorization is performed, requiring client certificates to have a specific organization field to access a matching pool of upstream servers. Security certificates and keys are stored locally on the server.

## Testing

Testing will be performed as follows:
- Basic unit tests will be provided for core methods and functions. These will not provide full coverage, but will cover the fundamentals (some edge cases, ). 
- Basic integration tests will be done as part of the implementation process, prior to upstream commits.

## Deployment and Operations

Docker will be used for basic deployment of the upstream servers and load-balancing server. Basic container networking and storage requirements will handled via Docker. A lightweight base image, such as Alpine will be preferred. This can be orchestrated via a simple Docker-Compose file.

## Scalability and Performance

The server is designed to be static in scale on the backend, but still handle concurrent client connections:
- The use of goroutines allows for handling each client connection in a separate thread.
- The rate limiter prevents clients from overwhelming the upstream servers with excessive requests.
- The forwarder and server pool manages upstream server connections and balances the load by selecting the server with the least connections.

## Future Extensibility

This design is limited in scope, and would potentially benefit from future enhancements such as:
- **Least-Connection Algo**: Implement a scalable least-connection forwarding algorithm behind the forwarder. This would require using a more advanced and scalable data structure to achieve O(log n) time. A self-balancing binary search tree - such as a red-black BST, left-leaning red-black tree or B-Tree would be good choice for expansion.
- **Rate-Limiter Algo**: Implement granular rate limiting algorithms that can scale with client count. Token bucket rate limiting would be a good first choice.
- **Client Authorization and ACLs**: Add support for more complex client authorization rules - such as ACL schemas based on client properties.
- **Enhanced Client-Server Protocol Support**: Support additional HTTP methods and data transfer protocols.
- **Configuration Management**: Add configuration loading and management using something like YAML or JSON configuration files.
- **Enhance Testing/CI Integration**: Expand unit and integration testing; include in a CI framework.
- **Health Checks and Monitoring**: Create methods and types to extract load balancer performance, upstream server health and client activity. Expose this data to observability and monitoring tools via APIs and appropriate network protocols.

## Conclusion

This design document provides a high-level overview of the layer 4/TCP load-balancing server and library. The scope of this design is one of basic functionality and simplicity, with the intent to provide a foundation to scale it's methods and properties if desired.
